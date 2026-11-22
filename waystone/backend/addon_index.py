"""The browsable addon index (see tools/build_addon_index.py).

A copy ships with the app; a fresher one is fetched from the repository at
most once a day and cached. Any failure falls back to what we have.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import net, paths

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "addon-index.json"
CACHED = paths.CACHE / "addon-index.json"
REMOTE = "https://raw.githubusercontent.com/stenberg82/waystone/main/waystone/data/addon-index.json"
MAX_AGE = 24 * 3600


@dataclass
class IndexAddon:
    repo: str
    name: str
    description: str
    stars: int
    updated: str
    version: str
    games: list[str]
    flavors: dict[str, list[int]] = field(default_factory=dict)


def _parse(data: dict) -> list[IndexAddon]:
    out = []
    for a in data.get("addons", []):
        try:
            out.append(IndexAddon(
                repo=a["repo"], name=a.get("name") or a["repo"].split("/")[-1],
                description=a.get("description", ""), stars=int(a.get("stars", 0)),
                updated=a.get("updated", ""), version=a.get("version", ""),
                games=list(a.get("games", [])), flavors=dict(a.get("flavors", {})),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _read(path: Path) -> tuple[str, list[IndexAddon]] | None:
    try:
        data = json.loads(path.read_text())
        return data.get("generated", ""), _parse(data)
    except (OSError, ValueError):
        return None


def load() -> list[IndexAddon]:
    """Newest of the cached and bundled index. Never touches the network."""
    best = None
    for path in (CACHED, BUNDLED):
        got = _read(path)
        if got and got[1] and (best is None or got[0] > best[0]):
            best = got
    return best[1] if best else []


def refresh() -> bool:
    """Fetch a newer index if the cache is older than a day. Returns True if updated."""
    try:
        if time.time() - CACHED.stat().st_mtime < MAX_AGE:
            return False
    except OSError:
        pass
    try:
        data = net.get_json(REMOTE)
    except Exception:
        CACHED.parent.mkdir(parents=True, exist_ok=True)
        if CACHED.exists():
            CACHED.touch()  # don't retry on every start while offline / private
        return False
    if not isinstance(data, dict) or not _parse(data):
        return False
    CACHED.parent.mkdir(parents=True, exist_ok=True)
    CACHED.write_text(json.dumps(data))
    return True
