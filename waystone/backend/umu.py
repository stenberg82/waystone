"""Locate or fetch umu-launcher, which manages Proton and the Steam runtime."""

from __future__ import annotations

import os
import shutil
import tarfile
import time
from pathlib import Path

from . import net, paths

VERSION_FILE = paths.UMU_DIR / ".version"
CHECK_STAMP = paths.CACHE / "umu-last-check"
CHECK_INTERVAL = 7 * 24 * 3600

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
    return _install(net.get_json(RELEASES_API), progress)


def maybe_update() -> str | None:
    """Weekly: refresh the bundled umu if a newer release exists.

    A system umu-run is left to the package manager. Returns the new tag
    when an update was installed. Caller must make sure nothing is running.
    """
    if shutil.which("umu-run") or not find():
        return None
    try:
        if time.time() - CHECK_STAMP.stat().st_mtime < CHECK_INTERVAL:
            return None
    except OSError:
        pass
    release = net.get_json(RELEASES_API)
    CHECK_STAMP.parent.mkdir(parents=True, exist_ok=True)
    CHECK_STAMP.touch()
    tag = release.get("tag_name") if isinstance(release, dict) else None
    current = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else None
    if not tag or tag == current:
        return None
    _install(release)
    return tag


def _install(release: object, progress: net.Progress | None = None) -> Path:
    assets = release.get("assets", []) if isinstance(release, dict) else []
    asset = next((a for a in assets if a.get("name", "").endswith("zipapp.tar")), None)
    if not asset:
        raise RuntimeError("Could not find a umu-launcher zipapp in the latest release.")

    archive = net.download(asset["browser_download_url"], paths.CACHE / asset["name"], progress)
    staging = paths.UMU_DIR.with_name("umu.new")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(staging, filter="data")
    archive.unlink(missing_ok=True)
    (staging / ".version").write_text(str(release.get("tag_name", "")))

    # Swap in only after a successful extract, so a failed update keeps the old one.
    if paths.UMU_DIR.exists():
        shutil.rmtree(paths.UMU_DIR)
    staging.rename(paths.UMU_DIR)

    found = find()
    if not found:
        raise RuntimeError("umu-run was not found after extracting umu-launcher.")
    found.chmod(0o755)
    return found
