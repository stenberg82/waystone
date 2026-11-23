"""Layered landscape behind the launcher, with a gentle pointer parallax.

The layers are Waystone's own SVGs (tools/make_ui_art.py). Each layer is
rasterised at the widget's size in a worker thread and drawn as a texture;
nearer layers move further when the pointer moves.
"""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Graphene, Gtk  # noqa: E402

ART = Path(__file__).resolve().parent / "art"
ASPECT = 900 / 1600                          # height / width of the SVG layers
DEPTH = (0.12, 0.25, 0.45, 0.7, 1.0)         # parallax per layer, back to front
SHIFT_X, SHIFT_Y = 26.0, 9.0                 # max offset of the nearest layer, px
COVER = 0.78                                 # the landscape covers at least this much height


class Landscape(Gtk.Widget):
    def __init__(self, game_id: str) -> None:
        super().__init__(hexpand=True, vexpand=True, can_target=False)
        self.files = sorted(ART.glob(f"land-{game_id}-*.svg"))
        self.textures: list[Gdk.Texture] = []
        self.tex_size: tuple[int, int] = (0, 0)   # logical size they were made for
        self.pending: tuple[int, int, int] | None = None
        self.target = [0.0, 0.0]
        self.pos = [0.0, 0.0]
        self.tick_id = 0
        self.generation = 0

    # ---------------------------------------------------------------- sizing

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        img_w = max(width + 2 * int(SHIFT_X) + 4, int(height * COVER / ASPECT))
        key = (img_w, int(img_w * ASPECT), self.get_scale_factor())
        if key[:2] != self.tex_size and key != self.pending:
            self.pending = key
            GLib.timeout_add(120, self._render_if_current, key)

    def _render_if_current(self, key) -> bool:
        if key == self.pending:
            self.generation += 1
            gen = self.generation
            threading.Thread(target=self._render, args=(key, gen), daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _render(self, key, gen: int) -> None:
        w, h, scale = key
        textures = []
        for f in self.files:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(f), w * scale, h * scale, False)
            except GLib.Error:
                continue
            fmt = (Gdk.MemoryFormat.R8G8B8A8 if pb.get_has_alpha() else Gdk.MemoryFormat.R8G8B8)
            textures.append(Gdk.MemoryTexture.new(pb.get_width(), pb.get_height(), fmt,
                                                  pb.read_pixel_bytes(), pb.get_rowstride()))
        GLib.idle_add(self._swap, gen, textures, (w, h))

    def _swap(self, gen: int, textures, size) -> bool:
        if gen == self.generation:
            self.textures, self.tex_size, self.pending = textures, size, None
            self.queue_draw()
        return GLib.SOURCE_REMOVE

    # ---------------------------------------------------------------- parallax

    def set_pointer(self, nx: float, ny: float) -> None:
        """Pointer position relative to the window centre, -1..1 on each axis."""
        self.target = [max(-1.0, min(1.0, nx)), max(-1.0, min(1.0, ny))]
        if not self.tick_id and self.get_mapped():
            self.tick_id = self.add_tick_callback(self._ease)

    def _ease(self, _widget, _clock) -> bool:
        done = True
        for i in (0, 1):
            d = self.target[i] - self.pos[i]
            if abs(d) > 0.002:
                self.pos[i] += d * 0.08
                done = False
            else:
                self.pos[i] = self.target[i]
        self.queue_draw()
        if done:
            self.tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    # ---------------------------------------------------------------- drawing

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        if not self.textures:
            return
        width, height = self.get_width(), self.get_height()
        img_w, img_h = self.tex_size
        for i, tex in enumerate(self.textures):
            depth = DEPTH[min(i, len(DEPTH) - 1)]
            x = (width - img_w) / 2 - self.pos[0] * SHIFT_X * depth
            y = height - img_h + SHIFT_Y - self.pos[1] * SHIFT_Y * depth
            rect = Graphene.Rect().init(x, y, img_w, img_h)
            snapshot.append_texture(tex, rect)
