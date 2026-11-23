"""Load the bundled fonts (SIL Open Font License, see data/fonts/*-OFL.txt).

Cinzel: carved Roman capitals for titles and buttons.
EB Garamond: a classic book face for longer text.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from pathlib import Path

import gi

gi.require_version("PangoCairo", "1.0")
from gi.repository import PangoCairo  # noqa: E402

FONT_DIR = Path(__file__).resolve().parent.parent / "data" / "fonts"


def load() -> None:
    """Make the bundled fonts available to GTK. Never fatal: without them
    the CSS falls back to the system's serif fonts."""
    files = sorted(FONT_DIR.glob("*.ttf"))
    fontmap = PangoCairo.FontMap.get_default()
    if hasattr(fontmap, "add_font_file"):          # Pango >= 1.56
        for f in files:
            try:
                fontmap.add_font_file(str(f))
            except Exception:
                pass
        return
    try:                                           # older Pango: via fontconfig
        fc = ctypes.CDLL(ctypes.util.find_library("fontconfig") or "libfontconfig.so.1")
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        for f in files:
            fc.FcConfigAppFontAddFile(None, str(f).encode())
    except OSError:
        pass
