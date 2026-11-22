"""High-level operations the UI drives: setup, login, install, play."""

from __future__ import annotations

import enum
import json
import shutil
import time
from typing import Callable

from .. import games
from . import fixes, net, paths, process, umu
from .config import Settings

INSTALLER_URL = "https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe"

Status = Callable[[str, float | None], None]   # (message, fraction or None = pulse)


class State(enum.Enum):
    SETUP = "setup"
    LOGIN = "login"
    WAITING_LOGIN = "waiting-login"
    INSTALL = "install"
    INSTALLING = "installing"
    READY = "ready"
    LAUNCHING = "launching"
    RUNNING = "running"


class Launcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = process.Runner(settings)
        self.launch_started: float | None = None
        self.install_requested: set[str] = set()

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
    def game_installed(game: games.Game) -> bool:
        folder = paths.WOW_DIR / game.folder
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
        if not self.game_installed(game):
            if bnet_open and game.id in self.install_requested:
                return State.INSTALLING
            self.install_requested.discard(game.id)
            return State.INSTALL
        return State.READY

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

    def open_battlenet(self, extra: list[str] | None = None) -> None:
        self.runner.spawn(paths.BNET_EXE, [*fixes.BATTLENET_ARGS, *(extra or [])])

    def install_game(self, game: games.Game) -> None:
        self.install_requested.add(game.id)
        self.open_battlenet([f"--game={game.launch_code}"])

    def play(self, game: games.Game) -> None:
        fixes.apply(game, self.settings)
        self.launch_started = time.monotonic()
        self.runner.spawn(
            paths.BNET_EXE,
            [*fixes.BATTLENET_ARGS, f"--exec=launch {game.launch_code}"],
            env=fixes.env(game),
        )

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
