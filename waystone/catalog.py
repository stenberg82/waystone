"""Curated popular addons that publish packaged releases on GitHub.

Each entry's ``games`` was checked against the addon's release.json
(BigWigs packager metadata) on 2026-11-22. Installing still re-checks the
live release, so an addon that drops support is refused, not mis-installed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogAddon:
    repo: str
    name: str
    blurb: str
    category: str
    games: tuple[str, ...]
    folder: str            # main AddOns folder, to detect manual installs


ALL = ("forever", "retail", "classic")

CATALOG: tuple[CatalogAddon, ...] = (
    CatalogAddon("Questie/Questie", "Questie", "Shows quests, objectives and turn-ins on the map.",
                 "Questing", ("forever", "classic"), "Questie"),
    CatalogAddon("BigWigsMods/BigWigs", "BigWigs", "Lightweight boss timers and warnings for raids.",
                 "Raiding", ALL, "BigWigs"),
    CatalogAddon("BigWigsMods/LittleWigs", "LittleWigs", "BigWigs timers for dungeons.",
                 "Dungeons", ALL, "LittleWigs"),
    CatalogAddon("DeadlyBossMods/DeadlyBossMods", "Deadly Boss Mods", "Classic boss warnings and timers.",
                 "Raiding", ALL, "DBM-Core"),
    CatalogAddon("DeadlyBossMods/DBM-Dungeons", "DBM Dungeons", "DBM modules for dungeons.",
                 "Dungeons", ALL, "DBM-Dungeons"),
    CatalogAddon("Tercioo/Plater-Nameplates", "Plater", "Highly customizable nameplates.",
                 "Interface", ALL, "Plater"),
    CatalogAddon("Nevcairiel/Bartender4", "Bartender4", "Flexible action bar replacement.",
                 "Interface", ALL, "Bartender4"),
    CatalogAddon("tullamods/Dominos", "Dominos", "Simple, movable action bars.",
                 "Interface", ALL, "Dominos"),
    CatalogAddon("WeakAuras/WeakAuras2", "WeakAuras", "Custom displays for buffs, cooldowns and more.",
                 "Interface", ("classic",), "WeakAuras"),
)


def for_game(game_id: str) -> list[CatalogAddon]:
    return [a for a in CATALOG if game_id in a.games]
