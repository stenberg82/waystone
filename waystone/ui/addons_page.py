"""Addons tab: list, install (GitHub / zip / drag & drop), update, remove."""

from __future__ import annotations

import threading
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import catalog, games
from ..backend import addons


def _pretty_version(v: str) -> str:
    return v.split("/")[-1].split("+")[0] if v else ""


class AddonsPage(Gtk.Box):
    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18, hexpand=True)
        self.add_css_class("addons-page")
        self.window = window
        self.game: games.Game = window.game
        self.items: list[addons.Addon] = []
        self.busy = False

        self.append(self._build_header())

        self.search = Gtk.SearchEntry(placeholder_text="Filter installed addons")
        self.search.add_css_class("addon-search")
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        self.append(self.search)

        self.content = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        self.discover_label = self._section("POPULAR ON GITHUB")
        body.append(self.discover_label)
        self.discover = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                    min_children_per_line=2, max_children_per_line=4,
                                    column_spacing=10, row_spacing=10)
        self.discover.add_css_class("discover")
        self.discover.set_vexpand(False)   # don't let cards stretch to fill the page
        self.discover.set_valign(Gtk.Align.START)
        body.append(self.discover)

        installed_label = self._section("INSTALLED")
        installed_label.set_margin_top(12)
        body.append(installed_label)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START)
        self.listbox.add_css_class("boxed-list")
        self.listbox.add_css_class("addon-list")
        self.listbox.set_filter_func(self._filter)
        body.append(self.listbox)
        self.empty = Gtk.Label(label="Nothing installed yet. Pick one above, add from GitHub, "
                                     "or drop a .zip file here.", xalign=0, wrap=True)
        self.empty.add_css_class("status-detail")
        body.append(self.empty)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(body)
        self.content.add_named(scroller, "list")

        self.missing = Adw.StatusPage(icon_name="folder-download-symbolic", title="Game not installed",
                                      description="Install the game first, then manage its addons here.")
        self.missing.add_css_class("addon-empty")
        self.content.add_named(self.missing, "missing")
        self.append(self.content)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

    # ------------------------------------------------------------------ layout

    def _build_header(self) -> Gtk.Widget:
        row = Gtk.Box(spacing=10)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        kicker = Gtk.Label(label="ADDONS", xalign=0)
        kicker.add_css_class("game-kicker")
        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class("addons-title")
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.add_css_class("status-detail")
        for w in (kicker, self.title, self.subtitle):
            texts.append(w)
        row.append(texts)

        actions = Gtk.Box(spacing=8, valign=Gtk.Align.END)
        self.refresh_btn = self._button("view-refresh-symbolic", "Check for updates", self._on_check)
        folder_btn = self._button("folder-open-symbolic", "Open AddOns folder", self._on_open_folder)
        file_btn = self._button(None, "Add .zip…", self._on_add_file)
        self.github_btn = Gtk.Button(label="Add from GitHub")
        self.github_btn.add_css_class("addon-primary")
        self.github_btn.connect("clicked", self._on_add_github)
        for w in (self.refresh_btn, folder_btn, file_btn, self.github_btn):
            actions.append(w)
        row.append(actions)
        return row

    @staticmethod
    def _section(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("section-label")
        lbl.set_margin_start(2)
        return lbl

    def _card(self, entry: catalog.CatalogAddon, installed: bool) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("addon-card")
        top = Gtk.Box(spacing=10)
        top.append(Adw.Avatar(text=entry.name, show_initials=True, size=34))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        name = Gtk.Label(label=entry.name, xalign=0, ellipsize=3)
        name.add_css_class("card-name")
        cat = Gtk.Label(label=entry.category, xalign=0)
        cat.add_css_class("card-cat")
        names.append(name)
        names.append(cat)
        top.append(names)
        card.append(top)
        blurb = Gtk.Label(label=entry.blurb, xalign=0, wrap=True, lines=2, ellipsize=3,
                          max_width_chars=28, vexpand=True, valign=Gtk.Align.START,
                          height_request=34)
        blurb.add_css_class("card-blurb")
        card.append(blurb)
        if installed:
            btn = Gtk.Button(label="Installed", sensitive=False)
            btn.add_css_class("card-installed")
        else:
            btn = Gtk.Button(label="Install")
            btn.add_css_class("addon-update")
            btn.connect("clicked", lambda _b: self._run(
                f"Installing {entry.name}…", lambda g: addons.install_github(g, entry.repo),
                lambda a: f"Installed {a.title}"))
        btn.set_sensitive(btn.get_sensitive() and not self.busy)
        card.append(btn)
        return card

    @staticmethod
    def _button(icon: str | None, text: str, cb) -> Gtk.Button:
        btn = Gtk.Button(icon_name=icon, tooltip_text=text) if icon else Gtk.Button(label=text)
        btn.add_css_class("addon-secondary")
        btn.connect("clicked", cb)
        return btn

    # ------------------------------------------------------------------ data

    def set_game(self, game: games.Game) -> None:
        self.game = game
        self.reload()

    def reload(self) -> None:
        game = self.game
        self.title.set_label(f"{game.short} addons")
        installed = self.window.launcher.game_installed(game, self.window.launcher.product(game))
        if not installed and not addons.addons_dir(game).is_dir():
            self.subtitle.set_label("")
            self.content.set_visible_child_name("missing")
            self._set_actions(False)
            return
        self._set_actions(not self.busy)
        self.items = addons.scan(game)
        iface = addons.game_interface(game)

        while (child := self.listbox.get_first_child()) is not None:
            self.listbox.remove(child)
        for item in self.items:
            self.listbox.append(self._row(item, iface))
        self.listbox.set_visible(bool(self.items))
        self.empty.set_visible(not self.items)

        keys = {a.key for a in self.items}
        folders = {f for a in self.items for f in a.folders}
        self.discover.remove_all()
        entries = catalog.for_game(game.id)
        for entry in entries:
            installed = f"github:{entry.repo.lower()}" in keys or entry.folder in folders
            self.discover.append(self._card(entry, installed))
        self.discover_label.set_visible(bool(entries))
        self.discover.set_visible(bool(entries))

        updates = sum(a.update_available for a in self.items)
        sub = f"{len(self.items)} installed"
        if updates:
            sub += f"  ·  {updates} update{'s' if updates > 1 else ''} available"
        if iface:
            sub += f"  ·  game interface {iface}"
        self.subtitle.set_label(sub)
        self.content.set_visible_child_name("list")

    def _set_actions(self, enabled: bool) -> None:
        for w in (self.refresh_btn, self.github_btn):
            w.set_sensitive(enabled)

    def _row(self, item: addons.Addon, iface: int | None) -> Gtk.Widget:
        meta = [v for v in (_pretty_version(item.version), item.author) if v]
        subtitle = "  ·  ".join(meta)
        if item.notes:
            subtitle = f"{subtitle} — {item.notes}" if subtitle else item.notes
        row = Adw.ActionRow(title=GLib.markup_escape_text(item.title),
                            subtitle=GLib.markup_escape_text(subtitle), subtitle_lines=1)
        row.addon = item
        row.add_prefix(Adw.Avatar(text=item.title, show_initials=True, size=38))

        if len(item.folders) > 1:
            row.add_suffix(self._pill(f"{len(item.folders)} modules", "neutral"))
        if item.source == "github":
            row.add_suffix(self._pill("GitHub", "neutral"))
        if addons.is_outdated(item, iface):
            pill = self._pill("Out of date", "warn")
            pill.set_tooltip_text("Made for another game version. It may still work if you "
                                  "enable 'Load out of date AddOns' in game.")
            row.add_suffix(pill)
        if item.update_available:
            upd = Gtk.Button(label=f"Update to {_pretty_version(item.latest)}", valign=Gtk.Align.CENTER)
            upd.add_css_class("addon-update")
            upd.connect("clicked", lambda _b, a=item: self._on_update(a))
            row.add_suffix(upd)

        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remove",
                            valign=Gtk.Align.CENTER)
        remove.add_css_class("flat")
        remove.connect("clicked", lambda _b, a=item: self._confirm_remove(a))
        row.add_suffix(remove)
        return row

    @staticmethod
    def _pill(text: str, kind: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, valign=Gtk.Align.CENTER)
        lbl.add_css_class("pill")
        lbl.add_css_class(kind)
        return lbl

    def _filter(self, row: Gtk.ListBoxRow) -> bool:
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        item = getattr(row, "addon", None)
        return bool(item) and (needle in item.title.lower()
                               or any(needle in f.lower() for f in item.folders))

    # ------------------------------------------------------------------ background work

    def _run(self, label: str, fn, done) -> None:
        if self.busy:
            self.window.toast("Please wait for the current addon task to finish.")
            return
        self.busy = True
        self._set_actions(False)
        self.subtitle.set_label(label)
        game = self.game

        def worker():
            try:
                result, error = fn(game), None
            except Exception as exc:
                result, error = None, str(exc)

            def finish():
                self.busy = False
                if error:
                    self.window.toast(error)
                elif done:
                    msg = done(result)
                    if msg:
                        self.window.toast(msg)
                if self.game is game:
                    self.reload()
                else:
                    self._set_actions(True)
            GLib.idle_add(finish)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ actions

    def _on_add_github(self, *_):
        entry = Gtk.Entry(placeholder_text="owner/name or https://github.com/…", activates_default=True)
        dialog = Adw.AlertDialog(
            heading="Add from GitHub",
            body=f"Paste a GitHub repository. Waystone picks the release built for {self.game.short}.",
            extra_child=entry, default_response="add", close_response="cancel")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Install")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_d, response):
            text = entry.get_text().strip()
            if response == "add" and text:
                self._run(f"Installing {text}…",
                          lambda g: addons.install_github(g, text),
                          lambda a: f"Installed {a.title}")
        dialog.connect("response", on_response)
        dialog.present(self.window)

    def _on_add_file(self, *_):
        zips = Gtk.FileFilter(name="Addon archives (.zip)")
        zips.add_suffix("zip")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(zips)
        dialog = Gtk.FileDialog(title="Choose addon .zip files", filters=filters, modal=True)
        dialog.open_multiple(self.window, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        self._install_files([Path(f.get_path()) for f in files if f.get_path()])

    def _on_drop(self, _target, value, _x, _y) -> bool:
        paths = [Path(f.get_path()) for f in value.get_files() if f.get_path()]
        zips = [p for p in paths if p.suffix.lower() == ".zip"]
        if not zips:
            self.window.toast("Drop .zip files with WoW addons.")
            return False
        self._install_files(zips)
        return True

    def _install_files(self, files: list[Path]) -> None:
        if not files:
            return

        def work(game):
            return [addons.install_zip(game, f).title for f in files]
        self._run("Installing…", work, lambda titles: "Installed " + ", ".join(titles))

    def _on_check(self, *_):
        self._run("Checking for updates…", addons.check_updates,
                  lambda n: f"{n} update{'s' if n != 1 else ''} available" if n else "Everything is up to date")

    def _on_update(self, item: addons.Addon) -> None:
        self._run(f"Updating {item.title}…", lambda g: addons.update(g, item),
                  lambda a: f"Updated {a.title} to {_pretty_version(a.version)}")

    def _confirm_remove(self, item: addons.Addon) -> None:
        folders = ", ".join(item.folders[:4]) + ("…" if len(item.folders) > 4 else "")
        dialog = Adw.AlertDialog(heading=f"Remove {item.title}?",
                                 body=f"Deletes these folders from AddOns: {folders}. "
                                      "Your saved settings for it are kept.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, r: r == "remove" and self._run(
            f"Removing {item.title}…", lambda g: addons.remove(g, item),
            lambda _r: f"Removed {item.title}"))
        dialog.present(self.window)

    def _on_open_folder(self, *_):
        folder = addons.addons_dir(self.game)
        folder.mkdir(parents=True, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(str(folder))).launch(self.window, None, None)
