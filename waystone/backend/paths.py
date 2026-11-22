"""Filesystem layout. Everything lives in one self-contained Wine prefix."""

from __future__ import annotations

import os
from pathlib import Path

APP_ID = "app.waystone.Waystone"


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / fallback


DATA = _xdg("XDG_DATA_HOME", ".local/share") / "waystone"
CONFIG = _xdg("XDG_CONFIG_HOME", ".config") / "waystone"
CACHE = _xdg("XDG_CACHE_HOME", ".cache") / "waystone"

PREFIX = DATA / "prefix"
UMU_DIR = DATA / "umu"
LOG_DIR = DATA / "logs"
LOG_FILE = LOG_DIR / "waystone.log"

DRIVE_C = PREFIX / "drive_c"
PROGRAM_FILES = DRIVE_C / "Program Files (x86)"
BNET_DIR = PROGRAM_FILES / "Battle.net"
BNET_EXE = BNET_DIR / "Battle.net.exe"
WOW_DIR = PROGRAM_FILES / "World of Warcraft"

BNET_INSTALL_PATH_WIN = r"C:\Program Files (x86)\Battle.net"


def battlenet_configs() -> list[Path]:
    users = DRIVE_C / "users"
    if not users.is_dir():
        return []
    return list(users.glob("*/AppData/Roaming/Battle.net/Battle.net.config"))


def ensure_dirs() -> None:
    for d in (DATA, CONFIG, CACHE, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
