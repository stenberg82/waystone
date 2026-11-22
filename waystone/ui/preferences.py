"""Preferences dialog."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gtk

from .. import games
from ..backend.config import Settings

AUTO_PROTONS = [("GE-Proton (latest, recommended)", "GE-Proton"), ("UMU-Proton (latest)", "UMU-Proton")]


def _local_protons() -> list[tuple[str, str]]:
    found = []
    roots = [
        Path.home() / ".steam/root/compatibilitytools.d",
        Path.home() / ".local/share/Steam/compatibilitytools.d",
        Path.home() / ".local/share/umu/compatibilitytools",
    ]
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            real = d.resolve()
            if (d / "proton").exists() and real not in seen:
                seen.add(real)
                found.append((d.name, str(d)))
    return found


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(self, settings: Settings, on_reset) -> None:
        super().__init__(title="Preferences", search_enabled=False)
        self.settings = settings

        page = Adw.PreferencesPage(title="General", icon_name="emblem-system-symbolic")
        self.add(page)

        compat = Adw.PreferencesGroup(title="Compatibility",
                                      description="Waystone runs Battle.net through Proton via umu-launcher.")
        page.add(compat)

        self.protons = AUTO_PROTONS + _local_protons()
        current = settings["proton"]
        if current not in [v for _, v in self.protons]:
            self.protons.append((current, current))
        combo = Adw.ComboRow(title="Proton version",
                             model=Gtk.StringList.new([n for n, _ in self.protons]))
        combo.set_selected([v for _, v in self.protons].index(current))
        combo.connect("notify::selected", self._on_proton)
        compat.add(combo)

        wayland = Adw.SwitchRow(title="Native Wayland",
                                subtitle="Experimental. Can improve smoothness on some setups.",
                                active=settings["wayland"])
        wayland.connect("notify::active", lambda r, _p: settings.__setitem__("wayland", r.get_active()))
        compat.add(wayland)

        graphics = Adw.PreferencesGroup(
            title="Graphics",
            description="DirectX 11 is slower but avoids crashes or flicker on some GPUs.")
        page.add(graphics)
        for game in games.GAMES:
            row = Adw.SwitchRow(title=f"Force DirectX 11 — {game.short}",
                                active=bool(settings.game(game.id).get("dx11")))
            row.connect("notify::active",
                        lambda r, _p, gid=game.id: settings.set_game(gid, "dx11", r.get_active()))
            graphics.add(row)

        danger = Adw.PreferencesGroup(title="Troubleshooting")
        page.add(danger)
        reset = Adw.ButtonRow(title="Reset Wine prefix…")
        reset.add_css_class("destructive-action")
        reset.connect("activated", lambda *_: self._confirm_reset(on_reset))
        danger.add(reset)

    def _on_proton(self, row: Adw.ComboRow, _pspec) -> None:
        self.settings["proton"] = self.protons[row.get_selected()][1]

    def _confirm_reset(self, on_reset) -> None:
        dialog = Adw.AlertDialog(
            heading="Reset the Wine prefix?",
            body="This removes Battle.net, your sign-in and all installed games inside Waystone. "
                 "You will have to set up and download everything again.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: r == "reset" and on_reset())
        dialog.present(self)
