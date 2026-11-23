Name:           waystone
Version:        0.1.0
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
