Name:           waystone
Version:        0.1.3
Release:        1%{?dist}
Summary:        Simple, good-looking launcher for World of Warcraft on Linux
License:        GPL-3.0-or-later
URL:            https://github.com/stenberg82/waystone
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  make
Requires:       python3 python3-gobject python3-cairo gtk4 libadwaita librsvg2
Requires:       vulkan-loader
Recommends:     umu-launcher

%description
Waystone sets up Battle.net in its own Proton prefix, lets you sign in once with
Blizzard's own login window, and then launches World of Warcraft with one click.

%prep
%autosetup

%install
make install DESTDIR=%{buildroot} PREFIX=%{_prefix}

%files
%license LICENSE
%doc README.md
%{_bindir}/waystone
%{_prefix}/lib/waystone/
%{_datadir}/applications/app.waystone.Waystone.desktop
%{_datadir}/metainfo/app.waystone.Waystone.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/app.waystone.Waystone.svg

%changelog
* Tue Nov 24 2026 Thomas <id+22034981+stenberg82@users.noreply.github.com> - 0.1.3-1
- Preferences: switch to turn off fsync, to try against the Battle.net
  sign-in hang

* Tue Nov 24 2026 Thomas <id+22034981+stenberg82@users.noreply.github.com> - 0.1.2-1
- Treat a Battle.net that lost its connection as signed out: Play waits for
  it to reconnect, then restarts it
- Read the running Battle.net session log, not the stub of a launch hand-off

* Tue Nov 24 2026 Thomas <id+22034981+stenberg82@users.noreply.github.com> - 0.1.1-1
- Restart a hung Battle.net also when it is opened from the menu, up to five
  starts, and stop its Agent too between starts
- Keep a first install in Installing until Battle.net says it is complete
- Keep download progress right across a restart of Waystone
- Use less memory for the landscapes of hidden games

* Mon Nov 23 2026 Thomas <id+22034981+stenberg82@users.noreply.github.com> - 0.1.0-1
- First release
