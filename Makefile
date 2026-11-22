PREFIX ?= /usr/local
DESTDIR ?=
SHARE = $(DESTDIR)$(PREFIX)/share
# Code goes to lib/waystone. Never share/waystone: that is where Waystone keeps
# its Wine prefix and games when PREFIX is ~/.local, and uninstall removes it.
APPDIR = $(DESTDIR)$(PREFIX)/lib/waystone

.PHONY: run install uninstall

run:
	./bin/waystone

install:
	rm -rf $(APPDIR)
	install -d $(APPDIR)
	cp -r waystone $(APPDIR)/
	find $(APPDIR) -name '__pycache__' -prune -exec rm -rf {} +
	install -Dm755 bin/waystone $(APPDIR)/bin/waystone
	install -d $(DESTDIR)$(PREFIX)/bin
	ln -sf ../lib/waystone/bin/waystone $(DESTDIR)$(PREFIX)/bin/waystone
	install -Dm644 data/app.waystone.Waystone.desktop $(SHARE)/applications/app.waystone.Waystone.desktop
	sed -i 's|^Exec=.*|Exec=$(PREFIX)/bin/waystone|' $(SHARE)/applications/app.waystone.Waystone.desktop
	install -Dm644 data/app.waystone.Waystone.metainfo.xml $(SHARE)/metainfo/app.waystone.Waystone.metainfo.xml
	install -Dm644 data/icons/app.waystone.Waystone.svg $(SHARE)/icons/hicolor/scalable/apps/app.waystone.Waystone.svg

uninstall:
	rm -rf $(APPDIR) $(DESTDIR)$(PREFIX)/bin/waystone \
	  $(SHARE)/applications/app.waystone.Waystone.desktop \
	  $(SHARE)/metainfo/app.waystone.Waystone.metainfo.xml \
	  $(SHARE)/icons/hicolor/scalable/apps/app.waystone.Waystone.svg
