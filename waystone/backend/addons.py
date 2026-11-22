"""Addon management: scan, install from zip / GitHub, update, remove.

Installed packages are tracked in ``Interface/AddOns/.waystone.json`` so a
multi-folder addon (e.g. DBM-Core + DBM-StatusBarTimers) shows up and is
updated/removed as one package. Addons installed by hand still show up,
one row per folder.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import games
from . import library, net, productdb

MANIFEST = ".waystone.json"
GITHUB_API = "https://api.github.com"

# Flavour-specific .toc suffixes, most specific first. Unsuffixed .toc is the fallback.
TOC_SUFFIXES: dict[str, tuple[str, ...]] = {
    "forever": ("_Forever", "-Forever", "_Camelot", "-Camelot"),
    "retail": ("_Mainline", "-Mainline"),
    "classic": ("_Mists", "-Mists", "_Cata", "-Cata", "_Classic", "-Classic",
                "_Wrath", "-WOTLKC", "_TBC", "-BCC", "_Vanilla", "-Classic"),
}

# Flavour names used by the BigWigs packager's release.json.
PACKAGER_FLAVORS: dict[str, tuple[str, ...]] = {
    "forever": ("forever", "camelot"),
    "retail": ("mainline", "retail"),
    "classic": ("mists", "cata", "wrath", "bcc", "classic", "vanilla"),
}

_COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t|\|A[^|]*\|a")


@dataclass
class Addon:
    key: str                     # package id or folder name
    title: str
    folders: list[str]
    version: str = ""
    author: str = ""
    notes: str = ""
    interfaces: list[int] = field(default_factory=list)
    source: str = "manual"       # manual | file | github
    repo: str = ""
    latest: str = ""             # newest known version (github)

    @property
    def update_available(self) -> bool:
        return bool(self.repo and self.latest and self.latest != self.version)


# ------------------------------------------------------------------ paths

def addons_dir(game: games.Game) -> Path:
    return library.game_dir(game) / "Interface" / "AddOns"


def game_interface(game: games.Game) -> int | None:
    product = productdb.find(game.launch_code, game.folder)
    return productdb.interface_number(product.version) if product and product.version else None


def is_outdated(addon: Addon, interface: int | None) -> bool:
    if not interface or not addon.interfaces:
        return False
    return all(i // 100 != interface // 100 for i in addon.interfaces)


# ------------------------------------------------------------------ manifest

def _manifest(game: games.Game) -> dict:
    try:
        return json.loads((addons_dir(game) / MANIFEST).read_text())
    except (OSError, ValueError):
        return {"packages": {}}


def _save_manifest(game: games.Game, data: dict) -> None:
    path = addons_dir(game) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


# ------------------------------------------------------------------ toc parsing

def _clean(text: str) -> str:
    return _COLOR.sub("", text).strip()


def _toc_for(folder: Path, game: games.Game) -> Path | None:
    name = folder.name
    for suffix in TOC_SUFFIXES.get(game.id, ()):
        cand = folder / f"{name}{suffix}.toc"
        if cand.is_file():
            return cand
    plain = folder / f"{name}.toc"
    if plain.is_file():
        return plain
    return next(iter(sorted(folder.glob("*.toc"))), None)


def read_toc(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return meta
    for line in lines:
        if line.startswith("##") and ":" in line:
            key, _, value = line[2:].partition(":")
            meta.setdefault(key.strip().lower(), value.strip())
    return meta


def _interfaces(value: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", value or "")]


def _folder_addon(folder: Path, game: games.Game) -> Addon | None:
    toc = _toc_for(folder, game)
    if not toc:
        return None
    meta = read_toc(toc)
    return Addon(
        key=folder.name,
        title=_clean(meta.get("title", "")) or folder.name,
        folders=[folder.name],
        version=_clean(meta.get("version", "")),
        author=_clean(meta.get("author", "")),
        notes=_clean(meta.get("notes", "")),
        interfaces=_interfaces(meta.get("interface", "")),
    )


# ------------------------------------------------------------------ scanning

def scan(game: games.Game) -> list[Addon]:
    root = addons_dir(game)
    if not root.is_dir():
        return []
    folders = {p.name: p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")}
    result: list[Addon] = []
    claimed: set[str] = set()

    for key, pkg in _manifest(game).get("packages", {}).items():
        present = [f for f in pkg.get("folders", []) if f in folders]
        if not present:
            continue
        claimed.update(present)
        main = _folder_addon(folders[present[0]], game)
        addon = Addon(
            key=key,
            title=pkg.get("name") or (main.title if main else key),
            folders=present,
            version=pkg.get("version", ""),
            author=main.author if main else "",
            notes=main.notes if main else "",
            interfaces=main.interfaces if main else [],
            source=pkg.get("source", "file"),
            repo=pkg.get("repo", ""),
            latest=pkg.get("latest", ""),
        )
        result.append(addon)

    for name, path in folders.items():
        if name in claimed:
            continue
        addon = _folder_addon(path, game)
        if addon:
            result.append(addon)

    result.sort(key=lambda a: a.title.lower())
    return result


# ------------------------------------------------------------------ installing

def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = []
    for info in zf.infolist():
        parts = Path(info.filename).parts
        if not parts or info.filename.startswith("/") or ".." in parts:
            raise ValueError(f"Unsafe path in archive: {info.filename}")
        members.append(info)
    return members


def install_zip(game: games.Game, archive: Path, *, key: str | None = None,
                name: str | None = None, source: str = "file", repo: str = "",
                version: str = "") -> Addon:
    """Install every top-level addon folder (one containing a .toc) from a zip."""
    root = addons_dir(game)
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf, tempfile.TemporaryDirectory(dir=root.parent) as tmp:
        zf.extractall(tmp, members=_safe_members(zf))
        staging = Path(tmp)
        # Some zips wrap everything in an extra folder (e.g. GitHub source zips).
        tops = [p for p in staging.iterdir() if p.is_dir()]
        addon_dirs = [p for p in tops if any(p.glob("*.toc"))]
        if not addon_dirs and len(tops) == 1:
            addon_dirs = [p for p in tops[0].iterdir() if p.is_dir() and any(p.glob("*.toc"))]
            if not addon_dirs and any(tops[0].glob("*.toc")):
                addon_dirs = tops
        if not addon_dirs:
            raise ValueError("That archive does not contain a WoW addon (no .toc file found).")

        folders = []
        for src in addon_dirs:
            dest = root / src.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(src), dest)
            folders.append(src.name)

    folders = _main_first(folders, repo.split("/")[-1] if repo else "")
    main = _folder_addon(root / folders[0], game)
    key = key or folders[0]
    data = _manifest(game)
    packages = data.setdefault("packages", {})
    # A folder belongs to one package only.
    for other_key, pkg in list(packages.items()):
        if other_key != key:
            pkg["folders"] = [f for f in pkg.get("folders", []) if f not in folders]
            if not pkg["folders"]:
                del packages[other_key]
    packages[key] = {
        "name": name or (main.title if main else key),
        "folders": folders,
        "source": source,
        "repo": repo,
        "version": version or (main.version if main else ""),
        "latest": version,
        "installed_at": int(time.time()),
    }
    _save_manifest(game, data)
    return next(a for a in scan(game) if a.key == key)


def _main_first(folders: list[str], hint: str) -> list[str]:
    """Order folders so the addon's main folder comes first: the one named
    like the repository, otherwise the shortest name (BigWigs before
    BigWigs_Core, Questie before QuestieDB)."""
    hint = hint.lower()
    exact = [f for f in folders if f.lower() == hint]
    rest = sorted((f for f in folders if f not in exact), key=lambda f: (len(f), f.lower()))
    return exact + rest


def remove(game: games.Game, addon: Addon) -> None:
    root = addons_dir(game)
    for folder in addon.folders:
        target = (root / folder).resolve()
        if target.parent == root.resolve() and target.is_dir():
            shutil.rmtree(target)
    data = _manifest(game)
    if data.get("packages", {}).pop(addon.key, None) is not None:
        _save_manifest(game, data)


# ------------------------------------------------------------------ GitHub

_REPO = re.compile(r"(?:github\.com[/:])?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def parse_repo(text: str) -> str:
    text = text.strip().split("#")[0].split("?")[0]
    text = re.sub(r"/(releases|tree|blob)(/.*)?$", "", text)
    m = _REPO.search(text)
    if not m:
        raise ValueError("Enter a GitHub repository like 'owner/name' or its URL.")
    return f"{m.group(1)}/{m.group(2)}"


def _latest_release(repo: str) -> dict:
    try:
        rel = net.get_json(f"{GITHUB_API}/repos/{repo}/releases/latest")
        if isinstance(rel, dict) and rel.get("assets") is not None:
            return rel
    except Exception:
        pass
    rels = net.get_json(f"{GITHUB_API}/repos/{repo}/releases?per_page=10")
    for rel in rels if isinstance(rels, list) else []:
        if not rel.get("draft"):
            return rel
    raise ValueError(f"{repo} has no releases to install.")


def _pick_asset(release: dict, game: games.Game) -> dict:
    assets = [a for a in release.get("assets", []) if a.get("name", "").lower().endswith(".zip")]
    if not assets:
        raise ValueError("The latest release has no .zip to install.")
    by_name = {a["name"]: a for a in assets}

    meta_asset = next((a for a in release.get("assets", []) if a.get("name") == "release.json"), None)
    if meta_asset:
        try:
            meta = net.get_json(meta_asset["browser_download_url"])
            iface = game_interface(game)
            flavors = PACKAGER_FLAVORS.get(game.id, ())
            entries = [e for e in meta.get("releases", []) if e.get("filename") in by_name]
            entries.sort(key=lambda e: bool(e.get("nolib")))  # prefer the full package

            def matches(e, test):
                return any(test(m) for m in e.get("metadata", []))

            if iface:
                for e in entries:
                    if matches(e, lambda m: int(m.get("interface", 0)) // 100 == iface // 100):
                        return by_name[e["filename"]]
            for e in entries:
                if matches(e, lambda m: str(m.get("flavor", "")).lower() in flavors):
                    return by_name[e["filename"]]
        except Exception:
            pass

    # No packager metadata: guess from file names.
    hints = PACKAGER_FLAVORS.get(game.id, ()) + tuple(s.strip("_-").lower() for s in TOC_SUFFIXES.get(game.id, ()))
    for a in assets:
        if any(h in a["name"].lower() for h in hints):
            return a
    others = set().union(*(v for k, v in PACKAGER_FLAVORS.items() if k != game.id))
    neutral = [a for a in assets if not any(h in a["name"].lower() for h in others)]
    if len(neutral) >= 1:
        return neutral[0]
    raise ValueError(f"No download for {game.short} in the latest release.")


def install_github(game: games.Game, text: str, progress: net.Progress | None = None) -> Addon:
    repo = parse_repo(text)
    release = _latest_release(repo)
    asset = _pick_asset(release, game)
    tag = release.get("tag_name") or release.get("name") or ""
    with tempfile.TemporaryDirectory() as tmp:
        archive = net.download(asset["browser_download_url"], Path(tmp) / asset["name"], progress)
        return install_zip(game, archive, key=f"github:{repo.lower()}", name=None,
                           source="github", repo=repo, version=tag)


def check_updates(game: games.Game) -> int:
    """Refresh 'latest' for GitHub packages. Returns how many have updates."""
    data = _manifest(game)
    count = 0
    for pkg in data.get("packages", {}).values():
        if pkg.get("source") != "github" or not pkg.get("repo"):
            continue
        try:
            rel = _latest_release(pkg["repo"])
        except Exception:
            continue
        pkg["latest"] = rel.get("tag_name") or pkg.get("latest", "")
        if pkg["latest"] and pkg["latest"] != pkg.get("version"):
            count += 1
    _save_manifest(game, data)
    return count


def update(game: games.Game, addon: Addon, progress: net.Progress | None = None) -> Addon:
    if not addon.repo:
        raise ValueError("Only addons installed from GitHub can be updated automatically.")
    old = set(addon.folders)
    new = install_github(game, addon.repo, progress)
    # Drop folders the new version no longer ships.
    root = addons_dir(game)
    for folder in old - set(new.folders):
        target = root / folder
        if target.is_dir():
            shutil.rmtree(target)
    return new
