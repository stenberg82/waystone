"""Locate or fetch umu-launcher, which manages Proton and the Steam runtime."""

from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path

from . import net, paths

RELEASES_API = "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"


def find() -> Path | None:
    system = shutil.which("umu-run")
    if system:
        return Path(system)
    if paths.UMU_DIR.is_dir():
        for candidate in paths.UMU_DIR.rglob("umu-run"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return None


def ensure(progress: net.Progress | None = None) -> Path:
    found = find()
    if found:
        return found

    release = net.get_json(RELEASES_API)
    assets = release.get("assets", []) if isinstance(release, dict) else []
    asset = next((a for a in assets if a.get("name", "").endswith("zipapp.tar")), None)
    if not asset:
        raise RuntimeError("Could not find a umu-launcher zipapp in the latest release.")

    archive = net.download(asset["browser_download_url"], paths.CACHE / asset["name"], progress)
    if paths.UMU_DIR.exists():
        shutil.rmtree(paths.UMU_DIR)
    paths.UMU_DIR.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(paths.UMU_DIR, filter="data")
    archive.unlink(missing_ok=True)

    found = find()
    if not found:
        raise RuntimeError("umu-run was not found after extracting umu-launcher.")
    found.chmod(0o755)
    return found
