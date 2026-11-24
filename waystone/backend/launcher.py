"""High-level operations the UI drives: setup, login, install, play."""

from __future__ import annotations

import enum
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from .. import games
from . import fixes, library, net, paths, process, productdb, umu
from .config import Settings

LOGIN_TIMEOUT = 120   # seconds Battle.net may take to sign in once it is up
START_TIMEOUT = 300   # seconds for Battle.net to appear; umu may fetch a new Proton first
STALL_SECONDS = 40    # its log silent this long while it spins the CPU = hung
BUSY_CPU = 0.5        # "spinning": at least half a core on average while silent
SIGN_IN_ATTEMPTS = 5  # Battle.net starts before giving up on a hung one
STUB_LOG_LINE = "Leaving because another instance of battle.net is running"
STUB_LOG_BYTES = 16384  # a hand-off stub log is ~2 KB; real sessions grow far past this
RECONNECT_SECONDS = 20  # for a Battle.net that lost its connection to sign in again by itself
PREFIX_EXIT_SECONDS = 15  # for Wine to wind down once Battle.net and its Agent are gone
# Blizzard sometimes checks a sign-in in a small popup. Wine's Wayland driver
# leaves it blank, so it never completes; on X11 it completes by itself.
CHALLENGE_LINE = "browser state changed: Challenge"
CHALLENGE_SECONDS = 10  # popup open this long under Wayland, still not signed in = stuck
X11_ENV = {"PROTON_ENABLE_WAYLAND": "0"}
GAME_START_SECONDS = 30   # for the game to appear after a launch command
UPDATE_STALL_SECONDS = 600  # an update before launch that makes no progress this long: give up

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


class SignIn(enum.Enum):
    OK = "ok"            # signed in
    STUCK = "stuck"      # hung (silent log, busy CPU) or exited: restart it
    TIMEOUT = "timeout"  # idle but not signed in: probably needs the user
    CHALLENGE = "challenge"  # Blizzard's check popup, which Wayland cannot draw


class Launcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runner = process.Runner(settings)
        self.launch_error: str | None = None
        self.launch_status: str | None = None   # shown while LAUNCHING
        self.launch_progress: float | None = None  # 0..1 while updating before a launch
        self.notice: str | None = None          # one-off message for the UI to toast
        self._worker: threading.Thread | None = None
        self._opener: threading.Thread | None = None
        self._cancel = threading.Event()
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
            return State.RUNNING
        if self.launching:
            return State.LAUNCHING
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
        # A first install looks finished before it starts: Battle.net writes
        # Wow.exe and flags the product installed+playable seconds before the
        # first byte counters reach product.db. Until a game has been seen
        # ready once, only update_complete counts as done.
        if not was_ready and (not product.update_complete if product
                              else game.id in self.install_requested):
            return State.INSTALLING if bnet_open else State.INSTALL
        if not self.game_installed(game, product):
            if bnet_open and game.id in self.install_requested:
                return State.INSTALLING
            self.install_requested.discard(game.id)
            return State.INSTALL
        if not was_ready:
            self.settings.set_game(game.id, "ready_once", True)
        return State.READY

    @property
    def launching(self) -> bool:
        return bool(self._worker and self._worker.is_alive() and not self._cancel.is_set())

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
        # The offset is the bytes on disk that are not this download (another
        # flavour's files in the shared folder). It stays the same for the whole
        # download, so it is saved and survives a restart of Waystone.
        key = {"uid": product.uid, "path": product.install_path, "total": total}
        if not calib:
            # First look: product.db may be minutes old. If nothing else lives
            # in this folder, every byte on disk belongs to this download.
            shared = any(p.install_path == product.install_path and p.uid != product.uid
                         for p in productdb.read())
            saved = self.settings.game(game.id).get("download_offset") or {}
            if not shared:
                offset = 0
            elif all(saved.get(k) == v for k, v in key.items()) and "offset" in saved:
                offset = saved["offset"]
            else:
                offset = size - db_done   # undercounts until product.db is next written
            calib = (mtime, offset)
            self._calibration[game.id] = calib
        elif calib[0] != mtime:
            # Fresh numbers from the Agent: re-anchor to them.
            calib = (mtime, size - db_done)
            self._calibration[game.id] = calib
            self.settings.set_game(game.id, "download_offset", {**key, "offset": calib[1]})
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
        """Show Battle.net. A cold start is watched from a thread, like Play
        does, so a Battle.net that hangs while signing in is restarted."""
        args = [*fixes.BATTLENET_ARGS, *(extra or [])]
        if self.battlenet_running():
            self.runner.spawn(paths.BNET_EXE, args, env=self._verb_env())
            return
        if self._opener and self._opener.is_alive():
            return
        if not self.launching:
            self._cancel.clear()
        self._opener = threading.Thread(target=self._open_worker, args=(args,), daemon=True)
        self._opener.start()

    def _open_worker(self, args: list[str]) -> None:
        try:
            if not self.logged_in():
                # No saved credentials: the user signs in in the window, and
                # Blizzard's popups (authenticator, checks) must be drawable,
                # so use X11. A quiet log means nothing here; just start it.
                self._ensure_battlenet(args, X11_ENV)
                return
            self._start_signed_in(args, report=lambda msg: setattr(self, "notice", msg))
        except Exception as exc:  # surfaced by the UI
            self.launch_error = str(exc)

    def install_game(self, game: games.Game) -> None:
        self.install_requested.add(game.id)
        self.open_battlenet([f"--game={game.launch_code}"])

    def play(self, game: games.Game) -> None:
        """Launch ``game``. Returns immediately; the work runs in a thread.

        Battle.net ignores --exec until it has signed in, so on a cold start
        we bring it up minimised (--autostarted), wait for the sign-in line in
        its log and only then hand it the launch command.
        """
        if self.launching:
            return
        fixes.apply(game, self.settings)
        self.launch_error = None
        self.launch_status = None
        self._cancel.clear()
        self._worker = threading.Thread(target=self._play_worker, args=(game,), daemon=True)
        self._worker.start()

    def _play_worker(self, game: games.Game) -> None:
        try:
            if not (self.battlenet_running() and self.battlenet_signed_in()):
                if not self._sign_in():
                    return
                time.sleep(2)  # let the client finish settling after sign-in
            product = self.product(game)
            uid = product.uid if product else ""
            attempts = updates = 0
            # Battle.net ignores a launch command while the game needs an
            # update; it updates first and does not launch afterwards, so the
            # command is sent again once the update is done.
            while attempts < 2 and updates < 3:
                if self._cancel.is_set():
                    return
                self.launch_status = f"Launching {game.short}…"
                self.launch_progress = None
                self.runner.spawn(
                    paths.BNET_EXE,
                    [*fixes.BATTLENET_ARGS, f"--exec=launch {game.launch_code}"],
                    env={**fixes.env(game), **self._verb_env()},
                )
                outcome = self._wait_for_game(game, uid)
                if outcome == "started":
                    if self.settings["close_battlenet"]:
                        time.sleep(3)  # let Battle.net hand over to the game
                        self.close_battlenet()
                    return
                if outcome == "stalled":
                    self.launch_error = (f"Battle.net is updating {game.short} but the update is not "
                                         "moving. Check Battle.net, then press Play again.")
                    self.open_battlenet()
                    return
                if outcome == "updated":
                    updates += 1
                else:
                    attempts += 1
            if not self._cancel.is_set():
                self.launch_error = "The game did not start. Try again, or open Battle.net from the menu."
        except Exception as exc:  # surfaced by the UI
            self.launch_error = str(exc)
        finally:
            self.launch_status = None
            self.launch_progress = None

    def _wait_for_game(self, game: games.Game, uid: str) -> str:
        """After a launch command: "started" once the game runs; "updated"
        when Battle.net has updated it meanwhile (send the command again);
        "stalled" if that update stops moving; "timeout" otherwise."""
        deadline = time.monotonic() + GAME_START_SECONDS
        updating = False
        last_done, moved_at = -1, time.monotonic()
        while not self._cancel.is_set():
            now = time.monotonic()
            if process.process_running(game.folder):
                return "started"
            if uid and self._game_updating(uid):
                if not updating and self.settings["close_battlenet"]:
                    # Waystone shows the progress; keep Battle.net out of sight.
                    # With HideOnClose this hides it and the update goes on.
                    self.close_battlenet()
                updating = True
                done = self._show_update_progress(game)
                if done != last_done:
                    last_done, moved_at = done, now
                elif now - moved_at >= UPDATE_STALL_SECONDS:
                    return "stalled"
                deadline = now + GAME_START_SECONDS
            elif updating:
                return "updated"
            if now > deadline or not self.battlenet_running():
                return "timeout"
            time.sleep(2)
        return "timeout"

    def _game_updating(self, uid: str) -> bool:
        """Is Battle.net updating ``uid`` right now, going by its log?"""
        log = self._session_log()
        try:
            text = log.read_text(errors="replace") if log else ""
        except OSError:
            return False
        return text.rfind(f"Update started: {uid}") > text.rfind(f"Update completed: {uid}")

    def _show_update_progress(self, game: games.Game) -> int:
        """Put the update's progress in the launch status. Returns a number
        that grows while the update moves (bytes done, or else the size of
        Battle.net's log, which logs as it updates), to tell a stalled one."""
        product = self.product(game)
        if product and product.total_bytes > 0:
            done, total = self.download_progress(game, product)
            self.launch_progress = max(0.0, min(done / total, 1.0))
            self.launch_status = f"Updating {game.short} before it starts… {self.launch_progress:.0%}"
            return done
        self.launch_progress = None
        self.launch_status = f"Updating {game.short} before it starts…"
        return self._log_size(0.0) or 0

    def _sign_in(self) -> bool:
        """Get a signed-in Battle.net, starting it if needed. A Battle.net that
        hangs (a Wine race, worse with ntsync) is restarted, up to
        SIGN_IN_ATTEMPTS starts in all. On failure sets launch_error and
        returns False."""
        if self.battlenet_running() and self._battlenet_disconnected():
            if not self._reconnect() or self._cancel.is_set():
                return False
            if self.battlenet_signed_in():
                return True
        self.launch_status = "Starting Battle.net and signing in…"
        result = self._start_signed_in([*fixes.BATTLENET_ARGS, "--autostarted"],
                                       report=lambda msg: setattr(self, "launch_status", msg))
        if result is SignIn.TIMEOUT:
            # Idle and still not signed in: it needs the user (password,
            # authenticator…), so show the window.
            self.launch_error = "Battle.net needs you to sign in. Then press Play again."
            self.open_battlenet()
        return result is SignIn.OK

    def _start_signed_in(self, args: list[str], report: Callable[[str], None]) -> SignIn | None:
        """Start Battle.net with ``args`` (unless it runs) and wait for it to
        sign in. A hung start is restarted, up to SIGN_IN_ATTEMPTS starts. If
        Blizzard's check popup comes up under Wayland, where it stays blank,
        Battle.net is restarted on X11 and shown, so the check can complete.
        Returns OK, TIMEOUT (it needs the user), or None if cancelled or it
        kept hanging (then with launch_error set)."""
        env: dict[str, str] | None = None
        attempt = 0
        while attempt < SIGN_IN_ATTEMPTS:
            since = self._ensure_battlenet(args, env)
            if since is None:
                return None
            result = self._wait_signed_in(since=since, timeout=LOGIN_TIMEOUT)
            if self._cancel.is_set():
                return None
            if result in (SignIn.OK, SignIn.TIMEOUT):
                return result
            if result is SignIn.CHALLENGE:
                process.Log.write("Battle.net is verifying the sign-in; restarting it on X11 "
                                  "so its check popup can show")
                report("Blizzard is verifying this sign-in. Opening Battle.net so the check can finish…")
                args = [a for a in args if a != "--autostarted"]
                env, attempt = X11_ENV, 0
            else:
                attempt += 1
                process.Log.write(f"Battle.net is not responding (start {attempt}/{SIGN_IN_ATTEMPTS})")
                if attempt < SIGN_IN_ATTEMPTS:
                    report(f"Battle.net stopped responding. Restarting it "
                           f"({attempt + 1}/{SIGN_IN_ATTEMPTS})…")
            if not self._kill_battlenet():
                break
        self._fail_stuck()
        return None

    def _reconnect(self) -> bool:
        """Battle.net lost its connection. Give it a moment to sign in again;
        if it does not, stop it so a fresh start can (its sign-in window can
        get stuck then). Returns False, with launch_error set, if it must be
        left alone because a game is running."""
        self.launch_status = "Battle.net lost its connection. Reconnecting…"
        deadline = time.monotonic() + RECONNECT_SECONDS
        while time.monotonic() < deadline:
            if self._cancel.is_set() or self.battlenet_signed_in():
                return True
            time.sleep(1)
        if any(process.process_running(g.folder) for g in games.GAMES):
            self.launch_error = ("Battle.net lost its connection and is signed out. "
                                 "Sign in in its window, then press Play again.")
            self.open_battlenet()
            return False
        process.Log.write("Battle.net did not reconnect; restarting it")
        self.launch_status = "Restarting Battle.net to sign in again…"
        return self._kill_battlenet() or self._fail_stuck()

    def _fail_stuck(self) -> bool:
        self.launch_error = ("Battle.net keeps getting stuck while starting. "
                             "Try again with Play, or open Battle.net from the menu.")
        return False

    def _ensure_battlenet(self, args: list[str] | None = None,
                          env: dict[str, str] | None = None) -> float | None:
        """Start Battle.net unless it runs (minimised by default, or with
        ``args``; ``env`` on top of the usual), and wait until its process is
        up. Returns the time to look for its session log from, or None (with
        launch_error set) if it never started."""
        if self.battlenet_running():
            return 0.0
        if not process.prefix_active(paths.PREFIX):
            library.apply_battlenet_defaults(self.library())
        since = time.time()
        if args is None:
            args = [*fixes.BATTLENET_ARGS, "--autostarted"]
        proc = self.runner.spawn(paths.BNET_EXE, args, env={**self._verb_env(), **(env or {})})
        # The clock for signing in starts only once Battle.net is up: before
        # that umu may spend a while downloading a new Proton.
        deadline = time.monotonic() + START_TIMEOUT
        while not self.battlenet_running():
            if self._cancel.is_set():
                return None
            if proc.poll() is not None or time.monotonic() > deadline:
                self.launch_error = "Battle.net did not start. See the log for details."
                return None
            time.sleep(1)
        return since

    @staticmethod
    def _kill_battlenet() -> bool:
        """Force-quit a hung Battle.net and its Agent, then wait for the
        prefix to empty so the next start is a clean one. Returns False if
        Battle.net itself would not die."""
        if not process.kill_processes("battle.net.exe"):
            return False
        # The Agent lives in C:/ProgramData/Battle.net/Agent/Agent.NNNN/.
        for token in ("battle.net/agent/", "battle.net\\agent\\"):
            process.kill_processes(token)
        deadline = time.monotonic() + PREFIX_EXIT_SECONDS
        while process.prefix_active(paths.PREFIX) and time.monotonic() < deadline:
            time.sleep(0.5)
        return True

    def close_battlenet(self) -> None:
        """Close the Battle.net window the polite way (like clicking ✕).

        Works on every desktop, unlike minimising, which some Wayland
        compositors ignore. Waystone keeps Battle.net's HideOnClose on, so it
        hides and keeps running (and updating) in the background. A running
        game is unaffected."""
        if self.battlenet_running():
            self.runner.spawn(Path("taskkill"), ["/IM", "Battle.net.exe"],
                              env={"PROTON_VERB": "runinprefix"})

    @staticmethod
    def _session_log(since: float = 0.0) -> Path | None:
        """The running Battle.net's log: the newest one, skipping the stubs
        that a second Battle.net (each --exec=launch hand-off) writes before
        it passes its command on and exits."""
        logs = []
        if paths.BNET_LOG_DIR.is_dir():
            for p in paths.BNET_LOG_DIR.glob("battle.net-*.log"):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if st.st_mtime >= since:
                    logs.append((st.st_mtime, st.st_size, p))
        for _mtime, size, p in sorted(logs, reverse=True):
            if size < STUB_LOG_BYTES:
                try:
                    if STUB_LOG_LINE in p.read_text(errors="replace"):
                        continue
                except OSError:
                    continue
            return p
        return None

    def _login_events(self, since: float = 0.0) -> tuple[int, int]:
        """Where in the session log the last sign-in and the last disconnect
        are (-1 if absent). Battle.net drops its connection now and then and
        logs a new sign-in when it gets back."""
        log = self._session_log(since)
        if not log:
            return -1, -1
        try:
            text = log.read_text(errors="replace")
        except OSError:
            return -1, -1
        return (text.rfind("Logged into Battle.net successfully"),
                text.rfind("Disconnected from Battle.net"))

    def battlenet_signed_in(self, since: float = 0.0) -> bool:
        """Is the running Battle.net session signed in right now?"""
        signed_in, disconnected = self._login_events(since)
        return signed_in > disconnected

    def _battlenet_disconnected(self) -> bool:
        """Signed in once this session, but lost the connection since."""
        signed_in, disconnected = self._login_events()
        return 0 <= signed_in < disconnected

    def _wait_signed_in(self, since: float, timeout: float) -> SignIn:
        """Wait for the sign-in line in Battle.net's log.

        Battle.net logs steadily while it starts and signs in. If the log
        goes quiet while the process keeps a core busy, it is hung; if it
        goes quiet while idle, it is most likely waiting for the user. A check
        popup that stays open under Wayland is reported as CHALLENGE."""
        start = time.monotonic()
        deadline = start + timeout
        last_size: int | None = None
        quiet_since, cpu_at_quiet = start, self._battlenet_cpu()
        challenge_since: float | None = None
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                return SignIn.TIMEOUT
            if self.battlenet_signed_in(since):
                return SignIn.OK
            if not self.battlenet_running():
                return SignIn.STUCK
            now = time.monotonic()
            if challenge_since is None:
                if self._log_has(since, CHALLENGE_LINE) and self._battlenet_on_wayland():
                    challenge_since = now
            elif now - challenge_since >= CHALLENGE_SECONDS:
                return SignIn.CHALLENGE
            size = self._log_size(since)
            if size != last_size:
                last_size = size
                quiet_since, cpu_at_quiet = now, self._battlenet_cpu()
            elif now - quiet_since >= STALL_SECONDS:
                busy = (self._battlenet_cpu() - cpu_at_quiet) / (now - quiet_since)
                if busy >= BUSY_CPU:
                    return SignIn.STUCK
            time.sleep(1)
        return SignIn.TIMEOUT

    def _log_has(self, since: float, line: str) -> bool:
        log = self._session_log(since)
        try:
            return bool(log) and line in log.read_text(errors="replace")
        except OSError:
            return False

    @staticmethod
    def _battlenet_on_wayland() -> bool:
        """Does the running Battle.net use Wine's Wayland driver?"""
        for pid in process.find_processes("battle.net.exe"):
            try:
                if b"winewayland" in Path(f"/proc/{pid}/maps").read_bytes():
                    return True
            except OSError:
                continue
        return False

    def _log_size(self, since: float) -> int | None:
        log = self._session_log(since)
        try:
            return log.stat().st_size if log else None
        except OSError:
            return None

    @staticmethod
    def _battlenet_cpu() -> float:
        return process.cpu_seconds(process.find_processes("battle.net.exe"))

    @staticmethod
    def _verb_env() -> dict[str, str]:
        # Proton's default verb (waitforexitandrun) blocks until everything in
        # the prefix has exited (Battle.net, its Agent, wineserver), so a launch
        # would just queue. runinprefix joins the running prefix instead.
        return {"PROTON_VERB": "runinprefix"} if process.prefix_active(paths.PREFIX) else {}

    def stop(self) -> None:
        self._cancel.set()
        self.launch_status = None
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
