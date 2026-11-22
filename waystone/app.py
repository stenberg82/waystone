"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from .backend import paths  # noqa: E402
from .backend.config import Settings  # noqa: E402


class WaystoneApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=paths.APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.settings: Settings | None = None
        self.window = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "ui" / "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.settings = Settings()
        for name, cb in (("preferences", self._on_preferences), ("about", self._on_about),
                         ("quit", lambda *_: self.quit())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.preferences", ["<Control>comma"])

    def do_activate(self) -> None:
        from .ui.window import MainWindow

        if not self.window:
            self.window = MainWindow(self, self.settings)
        self.window.present()

    def _on_preferences(self, *_):
        from .ui.preferences import PreferencesDialog

        def reset():
            self.window.launcher.reset_prefix()
            self.window.toast("Prefix removed. Run setup again.")
            self.window.refresh()

        PreferencesDialog(self.settings, reset).present(self.window)

    def _on_about(self, *_):
        Adw.AboutDialog(
            application_name="Waystone",
            application_icon=paths.APP_ID,
            version=__version__,
            developer_name="Waystone contributors",
            license_type=Gtk.License.GPL_3_0,
            comments="A simple launcher for World of Warcraft on Linux.\n\n"
                     "Not affiliated with or endorsed by Blizzard Entertainment. "
                     "World of Warcraft and Battle.net are trademarks of Blizzard Entertainment, Inc.",
        ).present(self.window)


def main() -> int:
    return WaystoneApp().run(sys.argv)
