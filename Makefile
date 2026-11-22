PREFIX ?= /usr/local
DESTDIR ?=
SHARE = $(DESTDIR)$(PREFIX)/share

.PHONY: run install uninstall

run:
	./bin/waystone

install:
	install -d $(SHARE)/waystone
	cp -r waystone $(SHARE)/waystone/
	find $(SHARE)/waystone -name '__pycache__' -prune -exec rm -rf {} +
	install -Dm755 bin/waystone $(SHARE)/waystone/bin/waystone
	install -d $(DESTDIR)$(PREFIX)/bin
	ln -sf ../share/waystone/bin/waystone $(DESTDIR)$(PREFIX)/bin/waystone
	install -Dm644 data/app.waystone.Waystone.desktop $(SHARE)/applications/app.waystone.Waystone.desktop
	install -Dm644 data/app.waystone.Waystone.metainfo.xml $(SHARE)/metainfo/app.waystone.Waystone.metainfo.xml
	install -Dm644 data/icons/app.waystone.Waystone.svg $(SHARE)/icons/hicolor/scalable/apps/app.waystone.Waystone.svg

uninstall:
	rm -rf $(SHARE)/waystone $(DESTDIR)$(PREFIX)/bin/waystone \
	  $(SHARE)/applications/app.waystone.Waystone.desktop \
	  $(SHARE)/metainfo/app.waystone.Waystone.metainfo.xml \
	  $(SHARE)/icons/hicolor/scalable/apps/app.waystone.Waystone.svg
