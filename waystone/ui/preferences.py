"""Preferences dialog."""

from __future__ import annotations

from pathlib import Path

from gi.repository import Adw, Gio, Gtk

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
    def __init__(self, settings: Settings, launcher, on_reset) -> None:
        super().__init__(title="Preferences", search_enabled=False)
        self.settings = settings
        self.launcher = launcher

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

        close_bnet = Adw.SwitchRow(title="Close Battle.net when the game starts",
                                   subtitle="Keeps the desktop tidy. The game keeps running.",
                                   active=settings["close_battlenet"])
        close_bnet.connect("notify::active",
                           lambda r, _p: settings.__setitem__("close_battlenet", r.get_active()))
        compat.add(close_bnet)

        lib = Adw.PreferencesGroup(
            title="Game library",
            description="Where Battle.net installs new games. Pick a folder on any disk "
                        "(ext4 or btrfs recommended). It shows up as drive W: in Battle.net.")
        page.add(lib)
        self.lib_row = Adw.ActionRow(title="Install location")
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._on_choose_library)
        self.lib_reset = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                                    tooltip_text="Use the default location")
        self.lib_reset.add_css_class("flat")
        self.lib_reset.connect("clicked", lambda *_: self._set_library(None))
        self.lib_row.add_suffix(self.lib_reset)
        self.lib_row.add_suffix(choose)
        lib.add(self.lib_row)
        self._update_library_row()

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

    def _update_library_row(self) -> None:
        current = self.settings["library"]
        self.lib_row.set_subtitle(current or "Default (inside Waystone's data folder)")
        self.lib_reset.set_visible(bool(current))

    def _on_choose_library(self, *_):
        dialog = Gtk.FileDialog(title="Choose a game library folder", modal=True)
        dialog.select_folder(self.get_root(), None, self._on_library_chosen)

    def _on_library_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except Exception:
            return  # cancelled
        if folder and folder.get_path():
            self._set_library(Path(folder.get_path()))

    def _set_library(self, folder):
        try:
            self.launcher.set_library(folder)
        except OSError as exc:
            self.add_toast(Adw.Toast(title=f"Could not use that folder: {exc}"))
            return
        self._update_library_row()
        if self.launcher.battlenet_running():
            self.add_toast(Adw.Toast(title="Restart Battle.net for the new location to apply."))

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
