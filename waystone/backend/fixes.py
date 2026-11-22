"""Per-game tweaks applied right before launch."""

from __future__ import annotations

import re

from .. import games
from . import library
from .config import Settings


def config_wtf(game: games.Game):
    return library.game_dir(game) / "WTF" / "Config.wtf"


def _set_cvar(text: str, name: str, value: str | None) -> str:
    pattern = re.compile(rf'^SET {re.escape(name)} ".*"\r?\n?', re.MULTILINE | re.IGNORECASE)
    text = pattern.sub("", text)
    if value is not None:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f'SET {name} "{value}"\n'
    return text


def apply(game: games.Game, settings: Settings) -> None:
    cfg = config_wtf(game)
    if not cfg.parent.parent.is_dir():
        return  # game not installed yet
    cfg.parent.mkdir(exist_ok=True)
    original = cfg.read_text(errors="replace") if cfg.exists() else ""
    if settings.game(game.id).get("dx11"):
        text = _set_cvar(original, "gxApi", "D3D11")
    elif re.search(r'^SET gxApi "D3D11"', original, re.MULTILINE | re.IGNORECASE):
        # Undo our override, but never touch an API the player picked in-game.
        text = _set_cvar(original, "gxApi", None)
    else:
        text = original
    if text != original:
        cfg.write_text(text)


def env(game: games.Game) -> dict[str, str]:
    return dict(game.env)


# Chromium flag for the Battle.net UI; avoids the blank white window under Wine.
BATTLENET_ARGS = ["--in-process-gpu"]
