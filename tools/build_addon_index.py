#!/usr/bin/env python3
"""Build waystone/data/addon-index.json from GitHub.

Finds WoW addon repositories by topic (sorted by stars), reads each latest
release's BigWigs-packager ``release.json`` and keeps only addons that
verifiably ship a build for Forever, Retail or Classic.

Needs a token for the API rate limit: GITHUB_TOKEN env var, or the gh CLI.
Run:  python3 tools/build_addon_index.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "waystone" / "data" / "addon-index.json"
API = "https://api.github.com"
TOPICS = ("wow-addon", "world-of-warcraft-addon", "warcraft-addon")
PAGES_PER_TOPIC = 3          # 100 results per page
MAX_AGE = timedelta(days=550)

# Which packager flavours / interface ranges count for each Waystone game.
FOREVER_FLAVORS = {"forever", "camelot"}
RETAIL_FLAVORS = {"mainline", "retail"}
CLASSIC_FLAVORS = {"mists", "cata", "wrath", "bcc"}


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("Set GITHUB_TOKEN or log in with the gh CLI.")


TOKEN = token()


def get(url: str, api: bool = True):
    headers = {"User-Agent": "Waystone-index-builder"}
    if api:
        headers |= {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 3:   # secondary rate limit
                time.sleep(20 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt == 3:
                return None
            time.sleep(2)
    return None


def search() -> dict[str, dict]:
    repos: dict[str, dict] = {}
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    for topic in TOPICS:
        for page in range(1, PAGES_PER_TOPIC + 1):
            data = get(f"{API}/search/repositories?q=topic:{topic}+archived:false+fork:false"
                       f"&sort=stars&order=desc&per_page=100&page={page}")
            items = (data or {}).get("items", [])
            for item in items:
                pushed = datetime.fromisoformat(item["pushed_at"].replace("Z", "+00:00"))
                if pushed >= cutoff:
                    repos.setdefault(item["full_name"].lower(), item)
            if len(items) < 100:
                break
            time.sleep(2)  # search API: 30 requests/minute with a token
    return repos


def flavors_for(entries: list[dict]) -> dict[str, list[int]]:
    """{'mainline': [120105, 120107], 'forever': [16001], ...}"""
    out: dict[str, set[int]] = {}
    for entry in entries:
        if entry.get("nolib"):
            continue
        for meta in entry.get("metadata", []):
            flavor = str(meta.get("flavor", "")).lower()
            if flavor:
                out.setdefault(flavor, set()).add(int(meta.get("interface", 0) or 0))
    return {k: sorted(v) for k, v in sorted(out.items())}


def games_for(entries: list[dict]) -> list[str]:
    found = set()
    for entry in entries:
        if entry.get("nolib"):
            continue
        for meta in entry.get("metadata", []):
            flavor = str(meta.get("flavor", "")).lower()
            iface = int(meta.get("interface", 0) or 0)
            if flavor in FOREVER_FLAVORS or iface // 100 == 160:
                found.add("forever")
            if flavor in RETAIL_FLAVORS:
                found.add("retail")
            if flavor in CLASSIC_FLAVORS:
                found.add("classic")
    return sorted(found)


def inspect(item: dict) -> dict | None:
    repo = item["full_name"]
    rel = get(f"{API}/repos/{repo}/releases/latest")
    if not rel or not rel.get("assets"):
        return None
    meta = next((a for a in rel["assets"] if a["name"] == "release.json"), None)
    if not meta:
        return None
    data = get(meta["browser_download_url"], api=False)
    if not isinstance(data, dict):
        return None
    entries = data.get("releases", [])
    games = games_for(entries)
    if not games:
        return None
    return {
        "repo": repo,
        "name": item["name"],
        "description": (item.get("description") or "").strip(),
        "stars": item["stargazers_count"],
        "updated": rel.get("published_at") or item["pushed_at"],
        "version": rel.get("tag_name", ""),
        "games": games,
        "flavors": flavors_for(entries),
    }


def main() -> None:
    repos = search()
    print(f"{len(repos)} candidate repositories", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [r for r in pool.map(inspect, repos.values()) if r]
    results.sort(key=lambda r: (-r["stars"], r["name"].lower()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "addons": results,
    }, indent=1, ensure_ascii=False) + "\n")
    counts = {g: sum(g in r["games"] for r in results) for g in ("forever", "retail", "classic")}
    print(f"{len(results)} verified addons -> {OUT.relative_to(ROOT)}  {counts}", file=sys.stderr)


if __name__ == "__main__":
    main()
