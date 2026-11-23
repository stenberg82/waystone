#!/usr/bin/env python3
"""Generate Waystone's UI art as SVG into waystone/ui/art/.

Everything here is drawn from scratch: noise textures, gold frame corners,
an ornamental divider, crest shields and procedural mountain landscapes.
No third-party or game assets are used. Re-run after changing a parameter:

    python3 tools/make_ui_art.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "waystone" / "ui" / "art"

GOLD = "#d9b46a"
GOLD_HI = "#f6e2a8"
GOLD_DIM = "#8a6d3b"


def svg(w: int, h: int, body: str, extra: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"{extra}>{body}</svg>\n')


# ------------------------------------------------------------------ textures

def stone() -> str:
    """Tileable dark-stone grain: fine speckle plus soft mottling."""
    return svg(256, 256, """
<filter id="fine" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="11" stitchTiles="stitch"/>
  <feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0.32 0 0 0 -0.12"/>
</filter>
<filter id="mottle" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="3" seed="4" stitchTiles="stitch"/>
  <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1.1 -0.42"/>
</filter>
<rect width="256" height="256" filter="url(#mottle)"/>
<rect width="256" height="256" filter="url(#fine)"/>""")


# ------------------------------------------------------------------ frame corners

def corner(rotate: int) -> str:
    """A 28px gold corner bracket with a small diamond, drawn for top-left
    and rotated for the other corners."""
    body = f"""
<g transform="rotate({rotate} 14 14)" fill="none" stroke-linecap="round">
  <path d="M2 18 V5 Q2 2 5 2 H18" stroke="{GOLD}" stroke-width="1.6"/>
  <path d="M6 22 V8 Q6 6 8 6 H22" stroke="{GOLD_DIM}" stroke-width="1"/>
  <path d="M9.5 6.5 L12 9 L9.5 11.5 L7 9 Z" transform="translate(0.5 0.5)" fill="{GOLD_HI}" stroke="none"/>
</g>"""
    return svg(28, 28, body)


# ------------------------------------------------------------------ divider

def divider() -> str:
    """Thin gold rule fading out at both ends, with a central diamond knot."""
    return svg(400, 16, f"""
<defs>
  <linearGradient id="fade" x1="0" x2="1">
    <stop offset="0" stop-color="{GOLD}" stop-opacity="0"/>
    <stop offset="0.35" stop-color="{GOLD}" stop-opacity="0.85"/>
    <stop offset="0.65" stop-color="{GOLD}" stop-opacity="0.85"/>
    <stop offset="1" stop-color="{GOLD}" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect x="0" y="7.5" width="185" height="1" fill="url(#fade)"/>
<rect x="215" y="7.5" width="185" height="1" fill="url(#fade)"/>
<path d="M200 2 L206 8 L200 14 L194 8 Z" fill="none" stroke="{GOLD}" stroke-width="1.2"/>
<path d="M200 5 L203 8 L200 11 L197 8 Z" fill="{GOLD_HI}"/>
<circle cx="188" cy="8" r="1.4" fill="{GOLD}"/>
<circle cx="212" cy="8" r="1.4" fill="{GOLD}"/>""", ' preserveAspectRatio="xMidYMid meet"')


# ------------------------------------------------------------------ crests

CRESTS = {
    "forever": ("#3ff0b0", "#11604f", "#5b3fc4"),
    "retail": ("#6aa8ff", "#1a3f9e", "#0d1f55"),
    "classic": ("#ffcf6e", "#b5601b", "#5a1d0c"),
}


def crest(top: str, mid: str, bottom: str) -> str:
    """A heater shield with a gold rim, filled with the game's colours."""
    shape = "M6 4 H50 Q52 4 52 6 V26 Q52 46 28 58 Q4 46 4 26 V6 Q4 4 6 4 Z"
    return svg(56, 62, f"""
<defs>
  <linearGradient id="fill" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="{top}"/><stop offset="0.55" stop-color="{mid}"/><stop offset="1" stop-color="{bottom}"/>
  </linearGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{GOLD_HI}"/><stop offset="0.5" stop-color="{GOLD}"/><stop offset="1" stop-color="{GOLD_DIM}"/>
  </linearGradient>
  <linearGradient id="shine" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity="0.35"/><stop offset="0.5" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
</defs>
<path d="{shape}" fill="url(#fill)" stroke="url(#rim)" stroke-width="2.4"/>
<path d="{shape}" fill="url(#shine)" transform="translate(28 31) scale(0.86) translate(-28 -31)"/>
<path d="{shape}" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="1"
      transform="translate(28 31) scale(0.9) translate(-28 -31)"/>""")


# ------------------------------------------------------------------ landscapes

W, H = 1600, 900


def ridge(rng: random.Random, base: float, rough: float, peaks: int, sharp: float) -> list[tuple[float, float]]:
    """A mountain ridgeline: a few big peaks plus midpoint-displacement detail."""
    anchors = [(0.0, base + rng.uniform(-rough, rough) * 0.4)]
    for i in range(1, peaks + 1):
        x = W * i / (peaks + 1) + rng.uniform(-W / (peaks * 4), W / (peaks * 4))
        anchors.append((x, base - rng.uniform(0.35, 1.0) * rough))
    anchors.append((float(W), base + rng.uniform(-rough, rough) * 0.4))
    pts = anchors
    amp = rough * 0.45
    for _ in range(6):
        out = [pts[0]]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2 + rng.uniform(-amp, amp) * sharp
            out += [(mx, my), (x2, y2)]
        pts = out
        amp *= 0.55
    return pts


def ridge_path(pts: list[tuple[float, float]]) -> str:
    d = f"M0 {H} L" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f" L{W} {H} Z"
    return d


def trees(rng: random.Random, pts: list[tuple[float, float]], count: int, size: tuple[float, float]) -> str:
    """Pine silhouettes standing on a ridge."""
    out = []
    for _ in range(count):
        i = rng.randrange(len(pts))
        x, y = pts[i]
        h = rng.uniform(*size)
        w = h * 0.32
        tiers = 3
        poly = []
        for t in range(tiers):
            ty = y - h * t / tiers
            tw = w * (1 - t / (tiers + 0.6))
            poly.append(f"M{x - tw:.1f} {ty + 2:.1f} L{x:.1f} {ty - h / tiers * 1.5:.1f} L{x + tw:.1f} {ty + 2:.1f} Z")
        out.append("".join(poly))
    return f'<path d="{"".join(out)}"/>'


def landscape_layers(game: str) -> list[str]:
    """Back-to-front SVG layers for one game (same size, transparent sky)."""
    rng = random.Random({"forever": 7, "retail": 21, "classic": 33}[game])
    pal = {
        "forever": ["#163f3a", "#0f2d2a", "#081d1c", "#030d0d"],
        "retail": ["#1a2a50", "#121e3c", "#0b1428", "#040913"],
        "classic": ["#4b2a16", "#341c0e", "#211107", "#0c0503"],
    }[game]
    mist = {"forever": "#7ff5cf", "retail": "#8fb8ff", "classic": "#ffb066"}[game]
    specs = [  # base y, roughness, peaks, sharpness, trees
        (560, 260, 4, 1.0, 0),
        (650, 170, 5, 0.9, 0),
        (735, 110, 6, 0.8, 40),
        (820, 70, 7, 0.7, 70),
    ]
    layers = []
    for n, ((base, rough, peaks, sharp, ntrees), color) in enumerate(zip(specs, pal)):
        pts = ridge(rng, base, rough, peaks, sharp)
        body = f"""
<defs>
  <linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{mist}" stop-opacity="{0.14 - n * 0.03:.3f}"/>
    <stop offset="0.45" stop-color="{mist}" stop-opacity="0"/>
  </linearGradient>
</defs>
<g fill="{color}">
  <path d="{ridge_path(pts)}"/>
  {trees(rng, pts, ntrees, (14 + n * 6, 30 + n * 12)) if ntrees else ""}
</g>
<path d="{ridge_path(pts)}" fill="url(#haze)"/>"""
        layers.append(svg(W, H, body, ' preserveAspectRatio="xMidYMax slice"'))
    return layers


def sky_details(game: str) -> str:
    """Behind the mountains: a moon or sun glow, and stars for Retail."""
    rng = random.Random(99)
    glow = {"forever": ("#b9ffe6", 1180, 230, 0.55), "retail": ("#e8f0ff", 1230, 200, 0.75),
            "classic": ("#ffcf80", 1290, 300, 0.8)}[game]
    color, cx, cy, op = glow
    stars = ""
    if game in ("retail", "forever"):
        n = 160 if game == "retail" else 70
        stars = "".join(
            f'<circle cx="{rng.uniform(0, W):.0f}" cy="{rng.uniform(0, 520):.0f}" '
            f'r="{rng.uniform(0.5, 1.6):.2f}" fill="#fff" fill-opacity="{rng.uniform(0.25, 0.9):.2f}"/>'
            for _ in range(n))
    disc = 46 if game != "classic" else 70
    return svg(W, H, f"""
<defs>
  <linearGradient id="fadeTop" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/>
    <stop offset="0.3" stop-color="#fff" stop-opacity="1"/>
  </linearGradient>
  <mask id="m"><rect width="{W}" height="{H}" fill="url(#fadeTop)"/></mask>
  <radialGradient id="g" cx="{cx}" cy="{cy}" r="420" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="{color}" stop-opacity="{op * 0.55:.2f}"/>
    <stop offset="0.25" stop-color="{color}" stop-opacity="{op * 0.18:.2f}"/>
    <stop offset="1" stop-color="{color}" stop-opacity="0"/>
  </radialGradient>
</defs>
<g mask="url(#m)">
{stars}
<circle cx="{cx}" cy="{cy}" r="420" fill="url(#g)"/>
<circle cx="{cx}" cy="{cy}" r="{disc}" fill="{color}" fill-opacity="{op:.2f}"/>
</g>""",
               ' preserveAspectRatio="xMidYMax slice"')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "stone.svg": stone(),
        "corner-tl.svg": corner(0),
        "corner-tr.svg": corner(90),
        "corner-br.svg": corner(180),
        "corner-bl.svg": corner(270),
        "divider.svg": divider(),
    }
    for game, colors in CRESTS.items():
        files[f"crest-{game}.svg"] = crest(*colors)
        files[f"land-{game}-0.svg"] = sky_details(game)
        for i, layer in enumerate(landscape_layers(game), start=1):
            files[f"land-{game}-{i}.svg"] = layer
    for name, text in files.items():
        (OUT / name).write_text(text)
    print(f"wrote {len(files)} files to {OUT}")


if __name__ == "__main__":
    main()
