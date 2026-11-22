"""Tiny HTTP helpers with progress reporting (stdlib only)."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Callable

USER_AGENT = "Waystone-Launcher"
Progress = Callable[[float | None], None]


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def get_json(url: str) -> object:
    with urllib.request.urlopen(_request(url), timeout=30) as resp:
        return json.load(resp)


def download(url: str, dest: Path, progress: Progress | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(_request(url), timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(256 * 1024):
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done / total if total else None)
    tmp.replace(dest)
    return dest
