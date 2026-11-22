"""Addons tab: installed addons and a browsable GitHub index."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .. import catalog, games
from ..backend import addon_index, addons

SORTS = (("popular", "Most popular"), ("updated", "Recently updated"), ("name", "Name"))
NICE_NAMES = {c.repo.lower(): c.name for c in catalog.CATALOG}


def _pretty_version(v: str) -> str:
    return v.split("/")[-1].split("+")[0] if v else ""


def _stars(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _ago(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    days = (datetime.now(timezone.utc) - then).days
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 45:
        return f"{days} days ago"
    if days < 365:
        months = max(days // 30, 1)
        return f"{months} month{'s' if months > 1 else ''} ago"
    return f"{days // 365} year{'s' if days >= 730 else ''} ago"


class AddonsPage(Gtk.Box):
    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16, hexpand=True)
        self.add_css_class("addons-page")
        self.window = window
        self.game: games.Game = window.game
        self.items: list[addons.Addon] = []
        self.index = addon_index.load()
        self.busy = False
        self.sort = "popular"

        self.append(self._build_header())
        self.append(self._build_toolbar())

        self.content = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.content.add_named(self._build_installed(), "installed")
        self.content.add_named(self._build_browse(), "browse")
        self.missing = Adw.StatusPage(icon_name="folder-download-symbolic", title="Game not installed",
                                      description="Install the game first, then manage its addons here.")
        self.missing.add_css_class("addon-empty")
        self.content.add_named(self.missing, "missing")
        self.append(self.content)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        threading.Thread(target=self._refresh_index, daemon=True).start()

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

    def _build_toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        self.view = Adw.ToggleGroup(css_classes=["ws-tabs", "round"], valign=Gtk.Align.CENTER)
        self.view.add(Adw.Toggle(name="installed", label="Installed"))
        self.view.add(Adw.Toggle(name="browse", label="Browse"))
        self.view.set_active_name("installed")
        self.view.connect("notify::active-name", self._on_view)
        bar.append(self.view)

        self.search = Gtk.SearchEntry(placeholder_text="Search installed addons", hexpand=True)
        self.search.add_css_class("addon-search")
        self.search.connect("search-changed", self._on_search)
        bar.append(self.search)

        self.sort_dd = Gtk.DropDown.new_from_strings([label for _, label in SORTS])
        self.sort_dd.add_css_class("addon-sort")
        self.sort_dd.set_tooltip_text("Sort")
        self.sort_dd.connect("notify::selected", self._on_sort)
        self.sort_dd.set_visible(False)
        bar.append(self.sort_dd)
        return bar

    def _build_installed(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.listbox = self._listbox(self._matches)
        box.append(self.listbox)
        self.empty = Gtk.Label(label="Nothing installed yet. Find something under Browse, "
                                     "add from GitHub, or drop a .zip file here.", xalign=0, wrap=True)
        self.empty.add_css_class("status-detail")
        box.append(self.empty)
        return self._scroll(box)

    def _build_browse(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.browse_note = Gtk.Label(xalign=0, wrap=True)
        self.browse_note.add_css_class("status-detail")
        box.append(self.browse_note)
        self.browse_list = self._listbox(self._matches)
        self.browse_list.set_sort_func(self._sort_browse)
        box.append(self.browse_list)
        return self._scroll(box)

    @staticmethod
    def _listbox(filter_func) -> Gtk.ListBox:
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START)
        lb.add_css_class("boxed-list")
        lb.add_css_class("addon-list")
        lb.set_filter_func(filter_func)
        return lb

    @staticmethod
    def _scroll(child: Gtk.Widget) -> Gtk.Widget:
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sw.set_child(child)
        return sw

    @staticmethod
    def _button(icon: str | None, text: str, cb) -> Gtk.Button:
        btn = Gtk.Button(icon_name=icon, tooltip_text=text) if icon else Gtk.Button(label=text)
        btn.add_css_class("addon-secondary")
        btn.connect("clicked", cb)
        return btn

    @staticmethod
    def _pill(text: str, kind: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, valign=Gtk.Align.CENTER)
        lbl.add_css_class("pill")
        lbl.add_css_class(kind)
        return lbl

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
        self.content.set_visible_child_name(self.view.get_active_name() or "installed")
        self.items = addons.scan(game)
        iface = addons.game_interface(game)

        self._clear(self.listbox)
        for item in self.items:
            self.listbox.append(self._installed_row(item, iface))
        self.listbox.set_visible(bool(self.items))
        self.empty.set_visible(not self.items)

        keys = {a.key for a in self.items}
        folders = {f.lower() for a in self.items for f in a.folders}
        self._clear(self.browse_list)
        available = [a for a in self.index if addons.supports(a.flavors, game, iface)]
        for entry in available:
            done = f"github:{entry.repo.lower()}" in keys or entry.name.lower() in folders
            self.browse_list.append(self._browse_row(entry, done))
        self.browse_note.set_label(
            f"{len(available)} addons on GitHub with a verified release for {game.short}. "
            "Compatibility is checked again when you install.")

        updates = sum(a.update_available for a in self.items)
        sub = f"{len(self.items)} installed"
        if updates:
            sub += f"  ·  {updates} update{'s' if updates > 1 else ''} available"
        if iface:
            sub += f"  ·  game interface {iface}"
        self.subtitle.set_label(sub)

    @staticmethod
    def _clear(lb: Gtk.ListBox) -> None:
        while (child := lb.get_first_child()) is not None:
            lb.remove(child)

    def _set_actions(self, enabled: bool) -> None:
        for w in (self.refresh_btn, self.github_btn):
            w.set_sensitive(enabled)

    def _refresh_index(self) -> None:
        if addon_index.refresh():
            def apply():
                self.index = addon_index.load()
                self.reload()
            GLib.idle_add(apply)

    # ------------------------------------------------------------------ rows

    def _installed_row(self, item: addons.Addon, iface: int | None) -> Gtk.Widget:
        meta = [v for v in (_pretty_version(item.version), item.author) if v]
        subtitle = "  ·  ".join(meta)
        if item.notes:
            subtitle = f"{subtitle} — {item.notes}" if subtitle else item.notes
        row = Adw.ActionRow(title=GLib.markup_escape_text(item.title),
                            subtitle=GLib.markup_escape_text(subtitle), subtitle_lines=1)
        row.search_text = " ".join([item.title, *item.folders]).lower()
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
        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remove", valign=Gtk.Align.CENTER)
        remove.add_css_class("flat")
        remove.connect("clicked", lambda _b, a=item: self._confirm_remove(a))
        row.add_suffix(remove)
        return row

    def _browse_row(self, entry: addon_index.IndexAddon, installed: bool) -> Gtk.Widget:
        name = NICE_NAMES.get(entry.repo.lower(), entry.name)
        row = Adw.ActionRow(title=GLib.markup_escape_text(name),
                            subtitle=GLib.markup_escape_text(entry.description or entry.repo),
                            subtitle_lines=2)
        row.entry = entry
        row.search_text = f"{name} {entry.repo} {entry.description}".lower()
        row.add_prefix(Adw.Avatar(text=name, show_initials=True, size=38))

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2)
        stars = Gtk.Label(label=f"★ {_stars(entry.stars)}", xalign=1)
        stars.add_css_class("browse-stars")
        when = Gtk.Label(label=_ago(entry.updated), xalign=1)
        when.add_css_class("browse-meta")
        meta.append(stars)
        meta.append(when)
        row.add_suffix(meta)

        link = Gtk.Button(icon_name="adw-external-link-symbolic", tooltip_text="Open on GitHub",
                          valign=Gtk.Align.CENTER)
        link.add_css_class("flat")
        link.connect("clicked", lambda _b: Gtk.UriLauncher.new(
            f"https://github.com/{entry.repo}").launch(self.window, None, None))
        row.add_suffix(link)

        if installed:
            btn = Gtk.Button(label="Installed", sensitive=False, valign=Gtk.Align.CENTER)
            btn.add_css_class("card-installed")
        else:
            btn = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, sensitive=not self.busy)
            btn.add_css_class("addon-update")
            btn.connect("clicked", lambda _b: self._run(
                f"Installing {name}…", lambda g: addons.install_github(g, entry.repo),
                lambda a: f"Installed {a.title}"))
        btn.set_size_request(96, -1)
        row.add_suffix(btn)
        return row

    # ------------------------------------------------------------------ filtering / sorting

    def _matches(self, row) -> bool:
        needle = self.search.get_text().strip().lower()
        return not needle or all(word in getattr(row, "search_text", "") for word in needle.split())

    def _sort_browse(self, a, b) -> int:
        ea, eb = a.entry, b.entry
        if self.sort == "updated":
            key_a, key_b = eb.updated, ea.updated
        elif self.sort == "name":
            key_a = NICE_NAMES.get(ea.repo.lower(), ea.name).lower()
            key_b = NICE_NAMES.get(eb.repo.lower(), eb.name).lower()
        else:
            key_a, key_b = -ea.stars, -eb.stars
        return (key_a > key_b) - (key_a < key_b)

    def _on_search(self, *_):
        self.listbox.invalidate_filter()
        self.browse_list.invalidate_filter()

    def _on_sort(self, dd, _pspec):
        self.sort = SORTS[dd.get_selected()][0]
        self.browse_list.invalidate_sort()

    def _on_view(self, group, _pspec):
        name = group.get_active_name() or "installed"
        self.sort_dd.set_visible(name == "browse")
        self.search.set_placeholder_text("Search GitHub addons" if name == "browse"
                                         else "Search installed addons")
        if self.content.get_visible_child_name() != "missing":
            self.content.set_visible_child_name(name)

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
                self._run(f"Installing {text}…", lambda g: addons.install_github(g, text),
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
        if files:
            self._run("Installing…", lambda g: [addons.install_zip(g, f).title for f in files],
                      lambda titles: "Installed " + ", ".join(titles))

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
