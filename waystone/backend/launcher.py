"""High-level operations the UI drives: setup, login, install, play."""

from __future__ import annotations

import enum
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable

from .. import games
from . import fixes, library, net, paths, process, productdb, umu
from .config import Settings

INSTALLER_URL = "https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe"

Status = Callable[[str, float | None], None]   # (message, fraction or None = pulse)


class State(enum.Enum):
    SETUP = "setup"
    LOGIN = "login"
    WAITING_LOGIN = "waiting-login"
    INSTALL = "install"
    INSTALLING = "installing"
    UPDATING = "updating"
    READY = "ready"
    LAUNCHING = "launching"
    RUNNING = "running"


class Launcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = process.Runner(settings)
        self.launch_started: float | None = None
        self.install_requested: set[str] = set()
        self._calibration: dict[str, tuple[float, int]] = {}

    # ---------- detection ----------

    @staticmethod
    def battlenet_installed() -> bool:
        return paths.BNET_EXE.is_file()

    @staticmethod
    def logged_in() -> bool:
        for cfg in paths.battlenet_configs():
            try:
                data = json.loads(cfg.read_text(errors="replace"))
            except (OSError, ValueError):
                continue
            if _find_key(data, "SavedAccountNames"):
                return True
        return False

    @staticmethod
    def product(game: games.Game) -> productdb.ProductStatus | None:
        return productdb.find(game.launch_code, game.folder)

    @staticmethod
    def game_installed(game: games.Game, product: productdb.ProductStatus | None = None) -> bool:
        if product and product.installed and product.playable:
            return True
        folder = library.game_dir(game, product)
        return folder.is_dir() and any(folder.glob("*.exe"))

    @staticmethod
    def battlenet_running() -> bool:
        return process.process_running("battle.net.exe")

    def state(self, game: games.Game) -> State:
        if not umu.find() or not self.battlenet_installed():
            return State.SETUP
        if process.process_running(game.folder):
            self.launch_started = None
            return State.RUNNING
        if self.launch_started and time.monotonic() - self.launch_started < 120:
            return State.LAUNCHING
        self.launch_started = None
        bnet_open = self.battlenet_running()
        if not self.logged_in():
            return State.WAITING_LOGIN if bnet_open else State.LOGIN
        product = self.product(game)
        # Battle.net flags a game installed+playable while the first download
        # is still running, so "downloading" is decided from the byte counters
        # and "install vs update" from whether we have ever seen it ready.
        downloading = bool(product and not product.update_complete and product.remaining_bytes > 0)
        was_ready = bool(self.settings.game(game.id).get("ready_once"))
        if downloading:
            return State.UPDATING if was_ready else State.INSTALLING
        if not self.game_installed(game, product):
            if bnet_open and game.id in self.install_requested:
                return State.INSTALLING
            self.install_requested.discard(game.id)
            return State.INSTALL
        if not was_ready:
            self.settings.set_game(game.id, "ready_once", True)
        return State.READY

    def download_progress(self, game: games.Game,
                          product: productdb.ProductStatus) -> tuple[int, int]:
        """(downloaded, total) bytes, live.

        The Agent only rewrites product.db every few minutes, so we measure
        bytes on disk and re-anchor against product.db whenever it changes
        (the Data folder is shared between WoW flavours, hence the offset).
        """
        total = product.total_bytes
        db_done = total - product.remaining_bytes
        root = library.game_root(game, product)
        try:
            mtime = productdb.PRODUCT_DB.stat().st_mtime
        except OSError:
            return db_done, total
        size = _allocated_size(root)
        calib = self._calibration.get(game.id)
        if not calib:
            # First look: product.db may be minutes old. If nothing else lives
            # in this folder, every byte on disk belongs to this download.
            shared = any(p.install_path == product.install_path and p.uid != product.uid
                         for p in productdb.read())
            calib = (mtime, size - db_done if shared else 0)
            self._calibration[game.id] = calib
        elif calib[0] != mtime:
            # Fresh numbers from the Agent: re-anchor to them.
            calib = (mtime, size - db_done)
            self._calibration[game.id] = calib
        live = size - calib[1]
        return max(db_done, min(live, total)), total

    # ---------- actions ----------

    def setup(self, status: Status) -> None:
        """Blocking. Fetches umu, downloads and runs the Battle.net installer."""
        paths.ensure_dirs()
        status("Fetching the Proton runtime manager…", None)
        umu.ensure(lambda f: status("Fetching the Proton runtime manager…", f))

        installer = paths.CACHE / "Battle.net-Setup.exe"
        if not installer.exists():
            net.download(INSTALLER_URL, installer,
                         lambda f: status("Downloading Battle.net…", f))

        status("Preparing Proton (first run downloads ~1 GB)…", None)
        done = {"rc": None}
        self.runner.spawn(
            installer,
            [f"--lang=enUS", f"--installpath={paths.BNET_INSTALL_PATH_WIN}"],
            on_line=lambda line: status(_short(line), None),
            on_exit=lambda rc: done.__setitem__("rc", rc),
        )
        # Battle.net.exe appears early while the installer is still unpacking,
        # so wait until the installer has finished or has started the client.
        while not (self.battlenet_installed()
                   and (done["rc"] is not None or self.battlenet_running())):
            if done["rc"] is not None and not self.battlenet_installed():
                raise RuntimeError(f"Battle.net installer exited ({done['rc']}). See the log.")
            time.sleep(1)
            status("Installing Battle.net – follow the Blizzard installer window…", None)
        status("Battle.net installed.", 1.0)

    def library(self) -> Path | None:
        lib = self.settings["library"]
        return Path(lib) if lib else None

    def set_library(self, folder: Path | None) -> None:
        """Use ``folder`` (any disk) for new game installs."""
        self.settings["library"] = str(folder) if folder else None
        library.set_library(folder)
        if not self.battlenet_running():
            library.apply_battlenet_defaults(folder)

    def use_existing(self, folder: Path, game: games.Game) -> list[games.Game]:
        """Make an existing WoW install reachable and open Battle.net so it
        can be located there. Returns the flavours found in that folder."""
        root, found = library.find_existing(folder)
        if not found:
            return []
        self.set_library(root.parent)
        target = next((g for g in found if g is game), found[0])
        self.open_battlenet([f"--game={target.launch_code}"])
        return found

    def open_battlenet(self, extra: list[str] | None = None) -> None:
        running = self.battlenet_running()
        if not running:
            library.apply_battlenet_defaults(self.library())
        self.runner.spawn(paths.BNET_EXE, [*fixes.BATTLENET_ARGS, *(extra or [])],
                          env=self._verb_env(running))

    def install_game(self, game: games.Game) -> None:
        self.install_requested.add(game.id)
        self.open_battlenet([f"--game={game.launch_code}"])

    def play(self, game: games.Game) -> None:
        fixes.apply(game, self.settings)
        running = self.battlenet_running()
        if not running:
            library.apply_battlenet_defaults(self.library())
        self.launch_started = time.monotonic()
        self.runner.spawn(
            paths.BNET_EXE,
            [*fixes.BATTLENET_ARGS, f"--exec=launch {game.launch_code}"],
            env={**fixes.env(game), **self._verb_env(running)},
        )

    @staticmethod
    def _verb_env(battlenet_running: bool) -> dict[str, str]:
        # Proton's default verb (waitforexitandrun) blocks until everything in
        # the prefix has exited, so with Battle.net already open a launch would
        # just queue forever. runinprefix hands the command to the running
        # Battle.net instead.
        return {"PROTON_VERB": "runinprefix"} if battlenet_running else {}

    def stop(self) -> None:
        self.launch_started = None
        self.runner.stop_all()

    def reset_prefix(self) -> None:
        self.stop()
        if paths.PREFIX.exists():
            shutil.rmtree(paths.PREFIX)


def _find_key(data: object, key: str) -> object:
    if isinstance(data, dict):
        for k, v in data.items():
            if k == key and v:
                return v
            found = _find_key(v, key)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_key(item, key)
            if found:
                return found
    return None


def _short(line: str, limit: int = 90) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"



def _allocated_size(root) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_blocks * 512
            except OSError:
                pass
    return total
