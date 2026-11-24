# Waystone

A simple, good-looking launcher for **World of Warcraft on Linux**: Forever, Retail and Classic.
Press **Set up**, sign in once, then press **Play**.

The theme changes with the selected game: background, ambient particles, accent colors and the Play button all follow along.

> Waystone is a fan project. It is not affiliated with or endorsed by Blizzard Entertainment.
> World of Warcraft and Battle.net are trademarks of Blizzard Entertainment, Inc.

## How it works

| Step | What happens |
|---|---|
| **Set up** | Downloads [umu-launcher](https://github.com/Open-Wine-Components/umu-launcher) (unless it is already on the system). umu fetches GE-Proton and the Steam Linux Runtime. Then it downloads and runs Blizzard's own Battle.net installer in a private Wine prefix. |
| **Log in** | Opens Blizzard's own Battle.net sign-in window. Waystone never sees your password. |
| **Install** | Opens Battle.net on the selected game so it can download it. |
| **Play** | Applies per-game fixes, then runs `Battle.net.exe --exec="launch <code>"`. |

Everything lives in `~/.local/share/waystone/` (Flatpak: `~/.var/app/app.waystone.Waystone/data/waystone/`).

### Per-game fixes

- **All games:** Battle.net gets `--in-process-gpu`, which avoids the blank white window.
- **Forever:** sets `WINE_SIMULATE_WRITECOPY=1`, a reported fix for GPU hangs.
- **Optional:** force DirectX 11 per game (writes `SET gxApi "D3D11"` to `Config.wtf`).
- **Optional:** native Wayland (`PROTON_ENABLE_WAYLAND=1`).
- **ntsync is off by default** (`PROTON_NO_NTSYNC=1`). With it, Battle.net often hangs right after "Connecting to server" and never signs in. It still hangs sometimes without it, so Waystone restarts a hung Battle.net (from Play and from the menu), up to five starts in all. You can turn ntsync back on in Preferences.

### Game library on another disk

- **Preferences → Game library:** pick any folder, for example on a second disk. Waystone maps it into the prefix as drive **W:** and sets it as Battle.net's default install location, so new installs go there.
- **Use existing installation…** (in the menu next to Play): point Waystone at an existing `World of Warcraft` folder, for example from Windows, Lutris or Steam. Waystone maps it, then you click **Locate the game** in Battle.net. Battle.net verifies the files and downloads only what is missing.

### Updates

- **Battle.net** updates itself inside the prefix, just like on Windows.
- **GE-Proton** is fetched in its latest version by umu.
- **umu-launcher:** a system copy is updated by the package manager. Otherwise Waystone checks for a newer release once a week and swaps it in only while nothing is running.

### Addons

The **Addons** tab, next to Play in the title bar, manages addons for the selected game:

- Lists everything in `Interface/AddOns`, reading each `.toc`. It understands flavour-specific files such as `_Forever`/`_Camelot`, `_Mainline` and `_Classic`.
- Flags addons built for another game version. The game's interface number comes from Battle.net, for example Forever 1.60.1 is 16001.
- **Add from GitHub:** paste `owner/name` or a URL. Waystone reads the packager's `release.json` to pick the zip for the right game.
- **Add .zip…** or drag and drop a zip file onto the page.
- Checks for updates, updates and removes addons. Multi-folder addons are handled as one package, tracked in `Interface/AddOns/.waystone.json`.

- **Browse:** search, and sort by most popular (GitHub stars), recently updated or name, among addons from `waystone/data/addon-index.json`.

The index lists addons tagged `wow-addon`, `world-of-warcraft-addon` or `warcraft-addon` on GitHub. An addon is included only if its latest release has a BigWigs-packager `release.json` that declares a build for Forever, Retail or Classic. Many Forever addons are new and ship without a `release.json`. These are included for Forever if a `.toc` in the released version declares a Forever interface (`## Interface: 16001`), and the release has a zip that Waystone would install for Forever. A copy ships with the app. A GitHub Action rebuilds the index daily (`tools/build_addon_index.py`), and the app fetches the fresh copy at most once a day.

CurseForge and Wago require approved API keys, so they are not supported.

### Product codes

| Game | Battle.net code | Folder |
|---|---|---|
| Forever | `WoWF` | `_forever_` |
| Retail | `WoW` | `_retail_` |
| Classic | `WoWC` | `_classic_` |

`WoWF` is verified against a live install of Forever 1.60.1.

## Install

**Fedora 43, 44 and 45** ([COPR](https://copr.fedorainfracloud.org/coprs/stenberg82/waystone/)):

```sh
sudo dnf copr enable stenberg82/waystone
sudo dnf install waystone
```

Other distros: build from `packaging/` or run from source, see below. Waystone is not on Flathub: Flathub accepts apps that run Windows programs through Wine only when the original developer submits them.

## Running from source

```sh
# Fedora
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita librsvg2
# Arch
sudo pacman -S python-gobject python-cairo gtk4 libadwaita librsvg

./bin/waystone
```

## Packaging

- **Flatpak** (all distros): `flatpak-builder --user --install build-dir packaging/flatpak/app.waystone.Waystone.yml`
- **Arch (AUR):** `packaging/arch/PKGBUILD`
- **Fedora (COPR):** `packaging/fedora/waystone.spec`
- **Releasing:** see [packaging/RELEASING.md](packaging/RELEASING.md)
- **Manual:** `make install PREFIX=~/.local` (just you) or `sudo make install` (system-wide). Uninstall the same way. Your Wine prefix and games in `~/.local/share/waystone` are never touched.


## Requirements

You need a GPU with Vulkan 1.3: AMD GCN 1+, NVIDIA Maxwell+ or Intel Skylake+, with current Mesa or NVIDIA drivers.
Keep the data folder on ext4 or btrfs, not NTFS.

## Status

Early prototype (0.1.2). Tested end to end against real Battle.net with Forever: set up, sign in, install and Play from a cold start. Retail and Classic are not tested yet.

## Art and fonts

All artwork is original and drawn in code: the landscapes, stone texture, frame corners, dividers and crests. `tools/make_ui_art.py` generates it as SVG into `waystone/ui/art/`. Waystone uses no game assets, logos, fonts or sounds from Blizzard.

The bundled fonts are licensed under the [SIL Open Font License 1.1](https://openfontlicense.org). The license texts are in `waystone/data/fonts/`.
- [Cinzel](https://github.com/NDISCOVER/Cinzel), by Natanael Gama and the Cinzel Project Authors
- [EB Garamond](https://github.com/octaviopardo/EBGaramond12), by Georg Duffner, Octavio Pardo and the EB Garamond Project Authors

## License

GPL-3.0-or-later
