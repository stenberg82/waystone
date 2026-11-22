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

### Game library on another disk

- **Preferences → Game library:** pick any folder, for example on a second disk. Waystone maps it into the prefix as drive **W:** and sets it as Battle.net's default install location, so new installs go there.
- **Use existing installation…** (in the menu next to Play): point Waystone at an existing `World of Warcraft` folder, for example from Windows, Lutris or Steam. Waystone maps it, then you click **Locate the game** in Battle.net. Battle.net verifies the files and downloads only what is missing.

### Updates

- **Battle.net** updates itself inside the prefix, just like on Windows.
- **GE-Proton** is fetched in its latest version by umu.
- **umu-launcher:** a system copy is updated by the package manager. Otherwise Waystone checks for a newer release once a week and swaps it in only while nothing is running.

### Product codes

| Game | Battle.net code | Folder |
|---|---|---|
| Forever | `WoWF` | `_forever_` |
| Retail | `WoW` | `_retail_` |
| Classic | `WoWC` | `_classic_` |

`WoWF` comes from community tooling and has not been verified against a live install yet.

## Running from source

```sh
# Fedora
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita
# Arch
sudo pacman -S python-gobject python-cairo gtk4 libadwaita

./bin/waystone
```

## Packaging

- **Flatpak** (all distros): `flatpak-builder --user --install build-dir packaging/flatpak/app.waystone.Waystone.yml`
- **Arch (AUR):** `packaging/arch/PKGBUILD`
- **Fedora (COPR):** `packaging/fedora/waystone.spec`
- **Manual:** `sudo make install` / `sudo make uninstall`


## Requirements

You need a GPU with Vulkan 1.3: AMD GCN 1+, NVIDIA Maxwell+ or Intel Skylake+, with current Mesa or NVIDIA drivers.
Keep the data folder on ext4 or btrfs, not NTFS.

## Status

Early prototype (0.1.0). The UI and the flow are done. The full end-to-end run against real Battle.net is still to be tested.

## License

GPL-3.0-or-later
