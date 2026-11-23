"""Run Windows executables in the Waystone prefix through umu-run."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from . import paths, umu
from .config import Settings

LineCallback = Callable[[str], None]
ExitCallback = Callable[[int], None]


class Log:
    _lock = threading.Lock()

    @classmethod
    def write(cls, line: str) -> None:
        paths.ensure_dirs()
        stamp = time.strftime("%H:%M:%S")
        with cls._lock, open(paths.LOG_FILE, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"[{stamp}] {line.rstrip()}\n")


class Runner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.procs: list[subprocess.Popen] = []

    def base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            WINEPREFIX=str(paths.PREFIX),
            GAMEID=str(self.settings["gameid"]),
            PROTONPATH=str(self.settings["proton"]),
            STORE="battlenet",
            WINEDEBUG=env.get("WINEDEBUG", "-all"),
        )
        if self.settings["wayland"]:
            env["PROTON_ENABLE_WAYLAND"] = "1"
        return env

    def spawn(
        self,
        exe: Path,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        on_line: LineCallback | None = None,
        on_exit: ExitCallback | None = None,
    ) -> subprocess.Popen:
        umu_run = umu.find()
        if not umu_run:
            raise RuntimeError("umu-run is not available. Run setup first.")
        full_env = self.base_env()
        full_env.update(env or {})
        cmd = [str(umu_run), str(exe), *(args or [])]
        Log.write("$ " + " ".join(cmd))
        if on_line is None:
            # Write straight to the log file: no pipe that could break (and
            # take Battle.net or the game down with SIGPIPE) if Waystone quits.
            paths.ensure_dirs()
            logfile = open(paths.LOG_FILE, "a", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(cmd, env=full_env, stdout=logfile, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            logfile.close()
            self.procs.append(proc)

            def wait() -> None:
                rc = proc.wait()
                Log.write(f"process exited with {rc}")
                if proc in self.procs:
                    self.procs.remove(proc)
                if on_exit:
                    on_exit(rc)

            threading.Thread(target=wait, daemon=True).start()
            return proc

        proc = subprocess.Popen(
            cmd,
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        self.procs.append(proc)

        def pump() -> None:
            assert proc.stdout
            for line in proc.stdout:
                Log.write(line)
                if on_line and line.strip():
                    on_line(line.strip())
            rc = proc.wait()
            Log.write(f"process exited with {rc}")
            if proc in self.procs:
                self.procs.remove(proc)
            if on_exit:
                on_exit(rc)

        threading.Thread(target=pump, daemon=True).start()
        return proc

    def alive(self) -> bool:
        return any(p.poll() is None for p in self.procs)

    def stop_all(self) -> None:
        for proc in list(self.procs):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


def find_processes(token: str) -> list[int]:
    """PIDs whose executable path (argv[0]) contains ``token``,
    case-insensitive. Wine processes show their Windows path there, e.g.
    'C:\\...\\_forever_\\Wow.exe'. Only argv[0] is checked so that shells or
    launchers merely *mentioning* the path don't count."""
    needle = token.lower().encode()
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv0 = (entry / "cmdline").read_bytes().split(b"\0", 1)[0]
        except OSError:
            continue
        if needle in argv0.lower():
            pids.append(int(entry.name))
    return pids


def process_running(token: str) -> bool:
    return bool(find_processes(token))


def cpu_seconds(pids: list[int]) -> float:
    """Total CPU time (user + system) the given processes have used so far."""
    ticks = 0
    for pid in pids:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            continue
        # The command name in field 2 may contain spaces; fields after it are fixed.
        fields = stat.rsplit(")", 1)[-1].split()
        ticks += int(fields[11]) + int(fields[12])  # utime, stime
    return ticks / os.sysconf("SC_CLK_TCK")


def kill_processes(token: str, timeout: float = 10.0) -> bool:
    """Force-quit every process matching ``token`` (see find_processes) and
    wait for them to go. For a hung program that ignores a polite close.
    Returns True once none are left."""
    for pid in find_processes(token):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(token):
            return True
        time.sleep(0.5)
    return False


def prefix_active(prefix: Path) -> bool:
    """True while anything (wineserver, Battle.net Agent, a game) runs in
    ``prefix``. Proton's default verb would block until all of it exits."""
    target = os.path.realpath(prefix)
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            env = (entry / "environ").read_bytes()
        except OSError:
            continue
        for var in env.split(b"\0"):
            if var.startswith(b"WINEPREFIX="):
                value = var[len(b"WINEPREFIX="):].decode(errors="replace")
                if os.path.realpath(value) == target:
                    return True
                break
    return False
