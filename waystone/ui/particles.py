"""Ambient particle layer whose look follows the selected game."""

from __future__ import annotations

import math
import random

import cairo
from gi.repository import GLib, Gtk

from ..games import ParticleStyle


class _P:
    __slots__ = ("x", "y", "vx", "vy", "r", "age", "life", "color", "phase", "fade")


class ParticleField(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.set_can_target(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.style: ParticleStyle | None = None
        self.parts: list[_P] = []
        self.last: float | None = None
        self.set_draw_func(self._draw)
        self.add_tick_callback(self._tick)

    def set_style(self, style: ParticleStyle) -> None:
        first = self.style is None
        self.style = style
        for p in self.parts:          # let the old palette fade out quickly
            p.fade = True
        if first:
            self.parts.clear()

    def _spawn(self, w: int, h: int, anywhere: bool) -> _P:
        s = self.style
        p = _P()
        p.x = random.uniform(0, w)
        speed = random.uniform(*s.rise)
        p.vy = -speed
        if anywhere:
            p.y = random.uniform(0, h)
        else:
            p.y = h + 10 if speed > 0 else random.uniform(0, h)
        p.vx = random.uniform(-s.drift, s.drift)
        p.r = random.uniform(*s.size)
        p.life = random.uniform(*s.life)
        p.age = random.uniform(0, p.life) if anywhere else 0.0
        p.color = random.choice(s.colors)
        p.phase = random.uniform(0, math.tau)
        p.fade = False
        return p

    def _tick(self, _widget, clock) -> bool:
        if not self.style:
            return GLib.SOURCE_CONTINUE
        now = clock.get_frame_time() / 1_000_000
        dt = 0.0 if self.last is None else min(now - self.last, 0.05)
        self.last = now
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return GLib.SOURCE_CONTINUE

        alive = []
        for p in self.parts:
            p.age += dt * (4.0 if p.fade else 1.0)
            p.x += (p.vx + math.sin(now * 0.6 + p.phase) * 4.0) * dt
            p.y += p.vy * dt
            if p.age < p.life and -20 < p.y < h + 20:
                alive.append(p)
        self.parts = alive

        fresh = sum(1 for p in self.parts if not p.fade)
        first_fill = not self.parts
        while fresh < self.style.count:
            self.parts.append(self._spawn(w, h, anywhere=first_fill or random.random() < 0.3))
            fresh += 1
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(self, _area, cr: cairo.Context, _w: int, _h: int) -> None:
        if not self.style:
            return
        cr.set_operator(cairo.OPERATOR_ADD)
        flicker = self.style.flicker
        t = self.last or 0.0
        for p in self.parts:
            a = math.sin(math.pi * min(p.age / p.life, 1.0)) * 0.85
            if flicker:
                a *= 1.0 - flicker * 0.5 * (1 + math.sin(t * 9.0 + p.phase * 3))
            if a <= 0.01:
                continue
            r, g, b = p.color
            glow = p.r * 5
            grad = cairo.RadialGradient(p.x, p.y, 0, p.x, p.y, glow)
            grad.add_color_stop_rgba(0, r, g, b, a * 0.55)
            grad.add_color_stop_rgba(1, r, g, b, 0)
            cr.set_source(grad)
            cr.arc(p.x, p.y, glow, 0, math.tau)
            cr.fill()
            cr.set_source_rgba(min(r + 0.3, 1), min(g + 0.3, 1), min(b + 0.3, 1), a)
            cr.arc(p.x, p.y, p.r * 0.6, 0, math.tau)
            cr.fill()
