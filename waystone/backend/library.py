"""Game library location: map any Linux folder (e.g. another disk) into the
prefix as drive W: and point Battle.net's default install path at it.

Also resolves Windows paths from Battle.net back to Linux paths, for any
drive letter in the prefix.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import games
from . import paths, productdb

LIBRARY_DRIVE = "w:"
DOSDEVICES = paths.PREFIX / "dosdevices"


def to_unix(win_path: str) -> Path | None:
    """'C:/Program Files (x86)/World of Warcraft' -> Linux path inside/outside the prefix."""
    if not win_path or len(win_path) < 2 or win_path[1] != ":":
        return None
    drive = DOSDEVICES / (win_path[0].lower() + ":")
    rest = win_path[2:].replace("\\", "/").lstrip("/")
    try:
        root = drive.resolve(strict=True)
    except OSError:
        if win_path[0].lower() == "c":
            root = paths.DRIVE_C
        else:
            return None
    return root / rest if rest else root


def to_windows(unix_path: Path) -> str:
    """Prefer the library drive when the path lives inside it, else Z:."""
    unix_path = unix_path.resolve()
    lib = DOSDEVICES / LIBRARY_DRIVE
    if lib.is_symlink():
        try:
            rel = unix_path.relative_to(lib.resolve())
            return LIBRARY_DRIVE.upper() + "/" + rel.as_posix() if str(rel) != "." else LIBRARY_DRIVE.upper() + "/"
        except ValueError:
            pass
    return "Z:" + unix_path.as_posix()


def game_root(game: games.Game, product: productdb.ProductStatus | None = None) -> Path:
    """The 'World of Warcraft' folder that holds this game's flavour folder."""
    product = product or productdb.find(game.launch_code, game.folder)
    if product:
        resolved = to_unix(product.install_path)
        if resolved:
            return resolved
    return paths.WOW_DIR


def game_dir(game: games.Game, product: productdb.ProductStatus | None = None) -> Path:
    return game_root(game, product) / game.folder


def set_library(folder: Path | None) -> None:
    """Map ``folder`` as W: (or remove the mapping when None)."""
    DOSDEVICES.mkdir(parents=True, exist_ok=True)
    link = DOSDEVICES / LIBRARY_DRIVE
    if link.is_symlink() or link.exists():
        link.unlink()
    if folder:
        folder.mkdir(parents=True, exist_ok=True)
        os.symlink(folder.resolve(), link)


def find_existing(folder: Path) -> tuple[Path, list[games.Game]]:
    """Given a folder the user picked, find the 'World of Warcraft' root and
    which flavours it contains. Accepts the root itself, a flavour folder
    (e.g. _retail_) or a parent that contains 'World of Warcraft'."""
    candidates = [folder, folder.parent, folder / "World of Warcraft"]
    for root in candidates:
        found = [g for g in games.GAMES if (root / g.folder).is_dir()]
        if found:
            return root, found
    return folder, []


def apply_battlenet_defaults(library: Path | None) -> None:
    """Write our preferences into Battle.net.config. Only call while
    Battle.net is not running – it rewrites the file on exit."""
    apply_account_defaults()
    target = to_windows(library) if library else "C:/Program Files (x86)"
    seen = set()
    for cfg in paths.battlenet_configs():
        real = cfg.resolve()
        if real in seen:
            continue
        seen.add(real)
        try:
            data = json.loads(real.read_text(errors="replace"))
        except (OSError, ValueError):
            continue
        client = data.setdefault("Client", {})
        install = client.setdefault("Install", {})
        if install.get("DefaultInstallPath") == target:
            continue
        install["DefaultInstallPath"] = target
        tmp = real.with_suffix(".waystone-tmp")
        tmp.write_text(json.dumps(data, indent=4))
        tmp.replace(real)


# Battle.net per-account settings (Roaming/Battle.net/<id>.config) we preset
# for new users only; a value the user has chosen is never overwritten.
ACCOUNT_DEFAULTS = {
    # Closing the window hides Battle.net instead of quitting, so a running
    # download keeps going while Waystone shows its progress.
    "HideOnClose": "true",
    "DisplayExitPrompt": "false",
}


def apply_account_defaults() -> None:
    """Only call while Battle.net is not running."""
    for cfg in paths.battlenet_configs():
        folder = cfg.resolve().parent
        for account_cfg in folder.glob("*.config"):
            if account_cfg.name == "Battle.net.config":
                continue
            try:
                data = json.loads(account_cfg.read_text(errors="replace"))
            except (OSError, ValueError):
                continue
            client = data.setdefault("User", {}).setdefault("Client", {})
            missing = {k: v for k, v in ACCOUNT_DEFAULTS.items() if k not in client}
            if not missing:
                continue
            client.update(missing)
            tmp = account_cfg.with_suffix(".waystone-tmp")
            tmp.write_text(json.dumps(data, indent=4))
            tmp.replace(account_cfg)
        break  # all user dirs point at the same folder
