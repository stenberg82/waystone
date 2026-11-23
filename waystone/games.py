"""Game definitions and per-game theming.

Product codes are the identifiers the Battle.net client understands in
``--exec="launch <code>"`` and ``--game=<code>``. ``WoWF`` (Forever) comes from
community tooling and should be verified against a live Battle.net install.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParticleStyle:
    colors: tuple[tuple[float, float, float], ...]
    count: int = 60
    rise: tuple[float, float] = (10.0, 30.0)   # px/s upwards (negative = falls)
    drift: float = 8.0                          # horizontal wander, px/s
    size: tuple[float, float] = (1.0, 2.6)
    life: tuple[float, float] = (6.0, 14.0)
    flicker: float = 0.0                        # 0..1, ember-like shimmer
    kind: str = "mote"                          # mote (rise), wisp (wander, pulse), ember (rise, cool)


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    short: str
    kicker: str
    tagline: str
    launch_code: str
    folder: str               # sub-folder inside "World of Warcraft"
    monogram: str
    chips: tuple[str, ...] = ()
    badge: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    particles: ParticleStyle = field(default_factory=lambda: ParticleStyle(((1, 1, 1),)))


FOREVER = Game(
    id="forever",
    name="World of Warcraft: Forever",
    short="Forever",
    kicker="AZEROTH, REBORN",
    tagline="The original world, levels 1–60, with new zones, dungeons and stories.",
    launch_code="WoWF",
    folder="_forever_",
    monogram="F",
    chips=("Levels 1–60", "9 new dungeons", "New race: Skyborne"),
    badge="NEW",
    # Reported fix for GPU hangs / crashes under Proton.
    env={"WINE_SIMULATE_WRITECOPY": "1"},
    particles=ParticleStyle(
        colors=((0.36, 0.95, 0.70), (0.55, 0.85, 1.0), (0.72, 0.55, 1.0)),
        count=46, rise=(-5.0, 7.0), drift=12.0, size=(1.4, 3.4), life=(9.0, 18.0), kind="wisp",
    ),
)

RETAIL = Game(
    id="retail",
    name="World of Warcraft",
    short="Retail",
    kicker="THE LIVING WORLD",
    tagline="The current expansion, the latest seasons and everything since 2004.",
    launch_code="WoW",
    folder="_retail_",
    monogram="W",
    chips=("Current expansion", "Mythic+", "Delves"),
    particles=ParticleStyle(
        colors=((0.45, 0.70, 1.0), (0.95, 0.80, 0.45), (0.75, 0.88, 1.0)),
        count=55, rise=(18.0, 42.0), drift=6.0, size=(0.8, 2.0), life=(5.0, 10.0),
    ),
)

CLASSIC = Game(
    id="classic",
    name="World of Warcraft Classic",
    short="Classic",
    kicker="AS IT WAS",
    tagline="Classic progression realms and Classic Era, as you remember them.",
    launch_code="WoWC",
    folder="_classic_",
    monogram="C",
    chips=("Progression realms", "Classic Era", "Hardcore"),
    particles=ParticleStyle(
        colors=((1.0, 0.62, 0.22), (1.0, 0.80, 0.40), (1.0, 0.45, 0.15)),
        count=65, rise=(14.0, 34.0), drift=10.0, size=(0.9, 2.4), life=(4.0, 9.0), flicker=0.6,
        kind="ember",
    ),
)

GAMES: tuple[Game, ...] = (FOREVER, RETAIL, CLASSIC)
BY_ID = {g.id: g for g in GAMES}


def get(game_id: str) -> Game:
    return BY_ID.get(game_id, FOREVER)
