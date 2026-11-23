"""Persistent user settings (JSON in $XDG_CONFIG_HOME/waystone)."""

from __future__ import annotations

import copy
import json
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "game": "forever",
    # "GE-Proton" / "UMU-Proton" make umu fetch the latest build automatically;
    # anything else is treated as a path to a Proton directory.
    "proton": "GE-Proton",
    "gameid": "umu-default",
    "wayland": False,
    # Battle.net often hangs while signing in when Proton uses ntsync, so it
    # is off unless the user turns it back on.
    "ntsync": False,
    "close_battlenet": True,
    # Linux folder mapped as drive W: for game installs (None = inside the prefix).
    "library": None,
    "games": {
        "forever": {"dx11": False},
        "retail": {"dx11": False},
        "classic": {"dx11": False},
    },
}


class Settings:
    def __init__(self) -> None:
        self.file = paths.CONFIG / "settings.json"
        self.data = copy.deepcopy(DEFAULTS)
        try:
            stored = json.loads(self.file.read_text())
            self._merge(self.data, stored)
        except (OSError, ValueError):
            pass

    @staticmethod
    def _merge(base: dict, extra: dict) -> None:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                Settings._merge(base[key], value)
            else:
                base[key] = value

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def game(self, game_id: str) -> dict[str, Any]:
        return self.data["games"].setdefault(game_id, {"dx11": False})

    def set_game(self, game_id: str, key: str, value: Any) -> None:
        self.game(game_id)[key] = value
        self.save()

    def save(self) -> None:
        paths.ensure_dirs()
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        tmp.replace(self.file)
