# Releasing Waystone

A checklist for each new version. `X.Y.Z` is the new version, for example `0.2.0`.
Nothing here is automated: every step that publishes something is a deliberate action.

## 1. Before the release

- [ ] `main` is clean and pushed, and the changes have been tried on the desktop.
      Test Play from the desktop, not from a terminal session: Battle.net hangs far more often there.
- [ ] Decide what goes in the release notes: new features, fixes, and what is still untested.

## 2. Bump the version

Change the version in these files:

| File | What to change |
|---|---|
| `waystone/__init__.py` | `__version__ = "X.Y.Z"` |
| `data/app.waystone.Waystone.metainfo.xml` | Add `<release version="X.Y.Z" date="YYYY-MM-DD"/>` at the top of `<releases>` |
| `packaging/fedora/waystone.spec` | `Version: X.Y.Z`, `Release: 1%{?dist}`, and a new `%changelog` entry at the top |
| `packaging/arch/PKGBUILD` | `pkgver=X.Y.Z`, `pkgrel=1` (the checksum follows in step 4) |
| `README.md` | The version under *Status*, if it is mentioned |

The Flatpak manifest builds from the checkout, so it needs no change.

## 3. Tag and release on GitHub

```sh
git commit -am "Release X.Y.Z"
git tag -a vX.Y.Z -m "Waystone X.Y.Z"
git push origin main vX.Y.Z
gh release create vX.Y.Z --title "Waystone X.Y.Z" --notes-file notes.md
```

Keep the note from earlier releases: *Waystone is a fan project. It is not affiliated with or endorsed by Blizzard Entertainment.*

## 4. Source checksum

The AUR package builds from the tag's tarball, so the checksum can only be computed after the tag is pushed:

```sh
curl -sL https://github.com/stenberg82/waystone/archive/vX.Y.Z.tar.gz | sha256sum
```

Put the value in `sha256sums` in `packaging/arch/PKGBUILD`, regenerate `.SRCINFO`, then commit and push:

```sh
cd packaging/arch && makepkg --printsrcinfo > .SRCINFO
```

## 5. Fedora COPR

Project: <https://copr.fedorainfracloud.org/coprs/stenberg82/waystone/> (Fedora 43, 44 and 45, x86_64).

- [ ] Check that the API key works: `copr-cli whoami` answers `stenberg82`.
      The key expires after 180 days. Renew it at <https://copr.fedorainfracloud.org/api/> and save it as `~/.config/copr` with mode 600.
- [ ] Download the tarball and build the source package:
      ```sh
      mkdir -p ~/rpmbuild/SOURCES
      curl -sL -o ~/rpmbuild/SOURCES/waystone-X.Y.Z.tar.gz \
        https://github.com/stenberg82/waystone/archive/vX.Y.Z/waystone-X.Y.Z.tar.gz
      rpmbuild -bs packaging/fedora/waystone.spec
      ```
- [ ] Upload and build: `copr-cli build waystone ~/rpmbuild/SRPMS/waystone-X.Y.Z-1.*.src.rpm`
- [ ] Check in a clean container for each Fedora version:
      ```sh
      podman run --rm registry.fedoraproject.org/fedora:44 bash -c \
        'dnf -y copr enable stenberg82/waystone && dnf -y install waystone && rpm -q waystone'
      ```
- [ ] When a new Fedora version comes out, add its chroot: `copr-cli modify waystone --chroot fedora-NN-x86_64 …`
      (list all chroots to keep, because the list replaces the old one). Drop versions that reach end of life.

## 6. AUR

Package: `waystone-launcher`, which conflicts with the unrelated AUR package `waystone`.
Not published yet (AUR account registration was closed in November 2026). The first push creates the package.

- [ ] Build in a clean Arch container and run `namcap`. It should report no errors (`E:`).
- [ ] Copy `PKGBUILD` and `.SRCINFO` into the AUR clone and push:
      ```sh
      git clone ssh://aur@aur.archlinux.org/waystone-launcher.git
      cp packaging/arch/{PKGBUILD,.SRCINFO} waystone-launcher/
      cd waystone-launcher && git commit -am "Update to X.Y.Z" && git push
      ```

## 7. After the release

- [ ] Check that <https://github.com/stenberg82/waystone/releases> shows the new version as *Latest*.
- [ ] Install from COPR on the desktop and try Play once.
