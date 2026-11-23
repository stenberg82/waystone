"""Main launcher window."""

from __future__ import annotations

import collections
import threading
import time
import traceback

from gi.repository import Adw, Gio, GLib, Gtk

from .. import games
from ..backend import library, paths
from ..backend.config import Settings
from ..backend.launcher import Launcher, State
from .particles import ParticleField

REFRESH_SECONDS = 2


class GameTile(Gtk.ToggleButton):
    def __init__(self, game: games.Game) -> None:
        super().__init__()
        self.game = game
        self.add_css_class("game-tile")

        row = Gtk.Box(spacing=12)
        mono = Gtk.Label(label=game.monogram)
        mono.add_css_class("monogram")
        mono.add_css_class(game.id)
        mono.set_valign(Gtk.Align.CENTER)
        row.append(mono)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=game.short, xalign=0)
        name.add_css_class("tile-name")
        sub = Gtk.Label(label=game.kicker.title(), xalign=0, ellipsize=3)
        sub.add_css_class("tile-sub")
        text.append(name)
        text.append(sub)
        text.set_hexpand(True)
        row.append(text)

        if game.badge:
            badge = Gtk.Label(label=game.badge, valign=Gtk.Align.CENTER)
            badge.add_css_class("badge")
            badge.add_css_class(f"static-{game.id}")
            row.append(badge)
        self.set_child(row)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, settings: Settings) -> None:
        super().__init__(application=app, title="Waystone")
        self.set_default_size(1180, 720)
        self.set_size_request(900, 600)
        self.add_css_class("waystone")

        self.settings = settings
        self.launcher = Launcher(settings)
        self.game = games.get(settings["game"])
        self.busy: tuple[str, float | None] | None = None
        self.state: State | None = None
        self.samples: dict[str, collections.deque] = {}

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        view = Adw.ToolbarView(extend_content_to_top_edge=True)
        header = Adw.HeaderBar()
        header.add_css_class("ws-header")
        header.pack_end(self._app_menu())
        self.tabs = Adw.ToggleGroup(css_classes=["ws-tabs", "round"])
        self.tabs.add(Adw.Toggle(name="play", label="Play"))
        self.tabs.add(Adw.Toggle(name="addons", label="Addons"))
        self.tabs.set_active_name("play")
        self.tabs.connect("notify::active-name", self._on_tab)
        header.set_title_widget(self.tabs)
        view.add_top_bar(header)
        view.set_content(self._build_body())
        self.toasts.set_child(view)

        self._install_actions()
        self._select_game(self.game, initial=True)
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)
        GLib.timeout_add_seconds(5, self._check_updates)

    # ------------------------------------------------------------------ layout

    def _build_body(self) -> Gtk.Widget:
        overlay = Gtk.Overlay()

        self.bg = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                            transition_duration=700, hexpand=True, vexpand=True)
        for game in games.GAMES:
            layer = Gtk.Box(hexpand=True, vexpand=True)
            layer.add_css_class(f"bg-{game.id}")
            self.bg.add_named(layer, game.id)
        overlay.set_child(self.bg)

        self.particles = ParticleField()
        overlay.add_overlay(self.particles)

        vignette = Gtk.Box(hexpand=True, vexpand=True, can_target=False)
        vignette.add_css_class("vignette")
        overlay.add_overlay(vignette)

        layout = Gtk.Box()
        layout.append(self._build_sidebar())
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=250, hexpand=True)
        self.pages.add_named(self._build_hero(), "play")
        from .addons_page import AddonsPage
        self.addons_page = AddonsPage(self)
        self.pages.add_named(self.addons_page, "addons")
        layout.append(self.pages)
        overlay.add_overlay(layout)
        return overlay

    def _build_sidebar(self) -> Gtk.Widget:
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=270)
        side.add_css_class("sidebar")

        brand = Gtk.Box(spacing=10, margin_start=6, margin_top=4)
        mark = Gtk.Label(label="◆")
        mark.add_css_class("brand-mark")
        name = Gtk.Label(label="WAYSTONE")
        name.add_css_class("brand")
        brand.append(mark)
        brand.append(name)
        side.append(brand)

        label = Gtk.Label(label="GAMES", xalign=0)
        label.add_css_class("section-label")
        side.append(label)

        self.tiles: dict[str, GameTile] = {}
        group: GameTile | None = None
        for game in games.GAMES:
            tile = GameTile(game)
            if group:
                tile.set_group(group)
            group = group or tile
            tile.connect("toggled", self._on_tile_toggled)
            self.tiles[game.id] = tile
            side.append(tile)

        side.append(Gtk.Box(vexpand=True))

        account = Gtk.Box(spacing=12)
        account.add_css_class("account")
        self.account_dot = Gtk.Box(valign=Gtk.Align.CENTER)
        self.account_dot.add_css_class("account-dot")
        account.append(self.account_dot)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        t = Gtk.Label(label="Battle.net", xalign=0)
        t.add_css_class("account-title")
        self.account_sub = Gtk.Label(label="Not signed in", xalign=0)
        self.account_sub.add_css_class("account-sub")
        texts.append(t)
        texts.append(self.account_sub)
        account.append(texts)
        side.append(account)
        return side

    def _build_hero(self) -> Gtk.Widget:
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        hero.add_css_class("hero")
        hero.append(Gtk.Box(vexpand=True))

        self.info = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                              transition_duration=450, vhomogeneous=False, interpolate_size=True)
        for game in games.GAMES:
            self.info.add_named(self._build_info(game), game.id)
        hero.append(self.info)

        hero.append(self._build_action_panel())
        return hero

    def _build_info(self, game: games.Game) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_bottom=34)
        kicker = Gtk.Label(label=game.kicker, xalign=0)
        kicker.add_css_class("game-kicker")
        title = Gtk.Label(label=game.name, xalign=0, wrap=True, max_width_chars=22)
        title.add_css_class("game-title")
        tagline = Gtk.Label(label=game.tagline, xalign=0, wrap=True, max_width_chars=60)
        tagline.add_css_class("game-tagline")
        chips = Gtk.Box(spacing=8, margin_top=8)
        for text in game.chips:
            chip = Gtk.Label(label=text)
            chip.add_css_class("chip")
            chips.append(chip)
        for w in (kicker, title, tagline, chips):
            box.append(w)
        return box

    def _build_action_panel(self) -> Gtk.Widget:
        panel = Gtk.Box(spacing=22, halign=Gtk.Align.START)
        panel.add_css_class("action-panel")

        split = Gtk.Box(spacing=2)
        self.play_button = Gtk.Button()
        self.play_button.add_css_class("play-button")
        inner = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        self.play_spinner = Adw.Spinner(visible=False)
        self.play_label = Gtk.Label(label="PLAY")
        inner.append(self.play_spinner)
        inner.append(self.play_label)
        self.play_button.set_child(inner)
        self.play_button.connect("clicked", self._on_primary)
        split.append(self.play_button)

        more = Gtk.MenuButton(icon_name="pan-down-symbolic", menu_model=self._game_menu(),
                              tooltip_text="More options")
        more.add_css_class("play-more")
        split.append(more)
        panel.append(split)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                         valign=Gtk.Align.CENTER, width_request=340)
        self.status_title = Gtk.Label(xalign=0)
        self.status_title.add_css_class("status-title")
        self.status_detail = Gtk.Label(xalign=0, wrap=True, max_width_chars=48)
        self.status_detail.add_css_class("status-detail")
        self.progress = Gtk.ProgressBar(visible=False, margin_top=6)
        self.progress.add_css_class("ws-progress")
        status.append(self.status_title)
        status.append(self.status_detail)
        status.append(self.progress)
        panel.append(status)
        return panel

    def _game_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        main = Gio.Menu()
        main.append("Open Battle.net", "win.open-battlenet")
        main.append("Install or repair game", "win.install-game")
        main.append("Use existing installation…", "win.use-existing")
        main.append("Open game folder", "win.open-folder")
        menu.append_section(None, main)
        danger = Gio.Menu()
        danger.append("Force quit", "win.stop")
        danger.append("Show log", "win.show-log")
        menu.append_section(None, danger)
        return menu

    def _app_menu(self) -> Gtk.MenuButton:
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About Waystone", "app.about")
        return Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True)

    def _install_actions(self) -> None:
        for name, cb in (
            ("open-battlenet", lambda *_: self._safe(self.launcher.open_battlenet)),
            ("install-game", lambda *_: self._safe(self.launcher.install_game, self.game)),
            ("open-folder", self._on_open_folder),
            ("use-existing", self._on_use_existing),
            ("stop", lambda *_: (self.launcher.stop(), self.refresh())),
            ("show-log", self._on_show_log),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)

    # ------------------------------------------------------------------ game switching

    def _on_tab(self, group, _pspec) -> None:
        name = group.get_active_name() or "play"
        self.pages.set_visible_child_name(name)
        if name == "addons":
            self.addons_page.set_game(self.game)

    def _on_tile_toggled(self, tile: GameTile) -> None:
        if tile.get_active() and tile.game is not self.game:
            self._select_game(tile.game)

    def _select_game(self, game: games.Game, initial: bool = False) -> None:
        for g in games.GAMES:
            self.remove_css_class(f"theme-{g.id}")
        self.add_css_class(f"theme-{game.id}")
        self.game = game
        self.tiles[game.id].set_active(True)
        self.bg.set_visible_child_name(game.id)
        self.info.set_visible_child_name(game.id)
        self.particles.set_style(game.particles)
        if hasattr(self, "addons_page") and self.pages.get_visible_child_name() == "addons":
            self.addons_page.set_game(game)
        elif hasattr(self, "addons_page"):
            self.addons_page.game = game
        if not initial:
            self.settings["game"] = game.id
        self.refresh()

    # ------------------------------------------------------------------ state rendering

    def _check_updates(self) -> bool:
        """Background weekly refresh of the bundled umu (never while running)."""
        from ..backend import process, umu

        if (self.busy or self.launcher.runner.alive()
                or self.launcher.battlenet_running() or process.process_running("wineserver")):
            return GLib.SOURCE_REMOVE

        def worker():
            try:
                tag = umu.maybe_update()
            except Exception as exc:  # offline etc. – try again next start
                process.Log.write(f"umu update check failed: {exc}")
                return
            if tag:
                GLib.idle_add(self.toast, f"Updated umu-launcher to {tag}")

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _tick(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        logged = self.launcher.logged_in()
        self.account_sub.set_label("Signed in" if logged else "Not signed in")
        if logged:
            self.account_dot.add_css_class("online")
        else:
            self.account_dot.remove_css_class("online")

        if self.busy:
            msg, frac = self.busy
            self._render("Working…", msg, "Please wait", enabled=False, spinner=True)
            self.progress.set_visible(True)
            if frac is None:
                self.progress.pulse()
            else:
                self.progress.set_fraction(frac)
            return

        self.progress.set_visible(False)
        g = self.game
        if self.launcher.launch_error:
            self.toast(self.launcher.launch_error)
            self.launcher.launch_error = None
        self.state = self.launcher.state(g)
        S = State
        table = {
            S.SETUP: ("Welcome to Waystone",
                      "One-time setup: downloads Proton and Battle.net (about 1.5 GB).",
                      "SET UP", True, False),
            S.LOGIN: ("Sign in to Battle.net",
                      "Use Blizzard's own sign-in window. You only need to do this once.",
                      "LOG IN", True, False),
            S.WAITING_LOGIN: ("Waiting for sign-in…",
                              "Finish signing in in the Battle.net window.",
                              "SIGNING IN", False, True),
            S.INSTALL: (f"{g.short} is not installed",
                        "Battle.net will download it. Keep the window open until it's done.",
                        "INSTALL", True, False),
            S.INSTALLING: (f"Installing {g.short}",
                           "Press Install in the Battle.net window to start the download.",
                           "INSTALLING", False, True),
            S.UPDATING: (f"Updating {g.short}", "Battle.net is downloading an update.",
                         "UPDATING", False, True),
            S.READY: ("Ready to play", g.name, "PLAY", True, False),
            S.LAUNCHING: ("Starting…",
                          self.launcher.launch_status
                          or "Signing in to Battle.net in the background and launching the game.",
                          "STARTING", False, True),
            S.RUNNING: ("Playing", "Have fun in Azeroth!", "PLAYING", False, False),
        }
        title, detail, label, enabled, spinner = table[self.state]
        self._render(title, detail, label, enabled, spinner)
        if self.state in (S.INSTALLING, S.UPDATING):
            self._render_download(g, label)
        else:
            self.samples.pop(g.id, None)

    def _render_download(self, game: games.Game, label: str) -> None:
        prod = self.launcher.product(game)
        if not prod or prod.total_bytes <= 0:
            return
        done, total = self.launcher.download_progress(game, prod)
        remaining = total - done
        frac = max(0.0, min(done / total, 1.0))

        now = time.monotonic()
        hist = self.samples.setdefault(game.id, collections.deque(maxlen=30))
        if not hist or hist[-1][1] != remaining:
            hist.append((now, remaining))
        while len(hist) > 2 and now - hist[0][0] > 30:
            hist.popleft()
        speed = 0.0
        if len(hist) >= 2 and hist[-1][0] > hist[0][0]:
            speed = (hist[0][1] - hist[-1][1]) / (hist[-1][0] - hist[0][0])

        detail = f"{_gb(done)} of {_gb(total)}"
        if speed > 0:
            detail += f"  ·  {speed / 1e6:.1f} MB/s  ·  {_eta(remaining / speed)} left"
        self.status_detail.set_label(detail)
        self.play_label.set_label(f"{label}  {frac:.0%}")
        self.progress.set_visible(True)
        self.progress.set_fraction(frac)

    def _render(self, title: str, detail: str, label: str, enabled: bool, spinner: bool) -> None:
        self.status_title.set_label(title)
        self.status_detail.set_label(detail)
        self.play_label.set_label(label)
        self.play_button.set_sensitive(enabled)
        self.play_spinner.set_visible(spinner)
        if spinner:
            self.play_button.add_css_class("busy")
        else:
            self.play_button.remove_css_class("busy")

    # ------------------------------------------------------------------ actions

    def _on_primary(self, _button) -> None:
        S = State
        if self.state == S.SETUP:
            self._run_task(self.launcher.setup, done="Battle.net is ready. Sign in in the Blizzard window.")
        elif self.state == S.LOGIN:
            self._safe(self.launcher.open_battlenet)
        elif self.state == S.INSTALL:
            self._safe(self.launcher.install_game, self.game)
        elif self.state == S.READY:
            self._safe(self.launcher.play, self.game)
        self.refresh()

    def _run_task(self, fn, done: str) -> None:
        def status(msg: str, frac: float | None) -> None:
            def apply():
                self.busy = (msg, frac)
                self.refresh()
            GLib.idle_add(apply)

        def worker():
            error = None
            try:
                fn(status)
            except Exception as exc:  # surfaced to the user as a toast
                traceback.print_exc()
                error = str(exc)

            def finish():
                self.busy = None
                self.toast(f"Something went wrong: {error}" if error else done)
                self.refresh()
            GLib.idle_add(finish)

        self.busy = ("Starting…", None)
        self.refresh()
        threading.Thread(target=worker, daemon=True).start()

    def _safe(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:
            self.toast(str(exc))
        self.refresh()

    def _on_open_folder(self, *_):
        folder = library.game_dir(self.game)
        target = folder if folder.exists() else paths.PREFIX
        if not target.exists():
            self.toast("Nothing installed yet.")
            return
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(target))).launch(self, None, None)

    def _on_use_existing(self, *_):
        dialog = Gtk.FileDialog(title="Select your World of Warcraft folder", modal=True)
        dialog.select_folder(self, None, self._on_existing_chosen)

    def _on_existing_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except Exception:
            return  # cancelled
        if not folder or not folder.get_path():
            return
        from pathlib import Path
        try:
            found = self.launcher.use_existing(Path(folder.get_path()), self.game)
        except Exception as exc:
            self.toast(str(exc))
            return
        if not found:
            self.toast("No World of Warcraft installation found in that folder.")
            return
        names = ", ".join(g.short for g in found)
        self._show_locate_help(names)
        self.refresh()

    def _show_locate_help(self, names: str) -> None:
        dialog = Adw.AlertDialog(
            heading="Almost there",
            body=f"Found: {names}.\n\nIn the Battle.net window, click “Locate the game” "
                 "under the Install button and choose\nW:\\World of Warcraft\n\n"
                 "Battle.net checks the files and only downloads what is missing.",
        )
        dialog.add_response("ok", "Got it")
        dialog.present(self)

    def _on_show_log(self, *_):
        if not paths.LOG_FILE.exists():
            self.toast("The log is empty.")
            return
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(paths.LOG_FILE))).launch(self, None, None)

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=5))


def _gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return "<1 min"
    h, m = divmod(seconds // 60, 60)
    return f"{h} h {m} min" if h else f"{m} min"
