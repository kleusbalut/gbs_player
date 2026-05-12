# <img src="images/icon.png" height=32px> GBS Player

[Japanese README (Japanese)](README.md)

GBS Player is a player tool for listening to GBS files.

<table>
<tr>
<td align=center><img src="images/2026-05-10 234235.png" height=200px></td>
<td align=center><img src="images/2026-05-10 230308.png" height=250px></td>
</tr>
<tr>
<td align=center>GBS Player screen example</td>
<td align=center>GBS Player for Android<br>(SameBoy core)</td>
</tr>
</table>

It can load GBS files and GB/GBC ROM files and use them like a music player.

## Documentation

- [Controls and option menu reference](docs/usage.en.md)
- [Android Player features (Japanese)](docs/android-player.md)
- [Supported character list (Japanese)](docs/usable-characters.md)
- [Song name / duration list format (Japanese)](docs/songlist-format.md)
- [Build information](docs/build.en.md)

### Supported Environments

- Real GB/GBC/GBA hardware
  - Requires a flash cart or equivalent device
- Analogue Pocket
- Emulators
- Android Player with the custom SameBoy core

## Main Features

### GBS Player ROM

- Controls inspired by late-1990s Game Boy RPGs.
- Includes per-song duration settings, playlists, repeat modes, fade-out, silence detection, and stereo/mono output.
  - See [Controls](docs/usage.en.md) for details.
- Long song titles scroll automatically.
- Song names can use hiragana, katakana, alphanumeric characters, and supported symbols.

### GUI Tool

The included GUI can edit song names, playlists, build settings, and also build and install the Android Player.

<img src="images/2026-05-10 230857.png" height=300px>

### Android Player

The Android app can be built as a standalone music player. It runs the generated ROM through a built-in Game Boy emulator based on SameBoy.

#### Android Media Controls

<img src="images/2026-05-11 003529.png" height=100px>

Playback can be controlled through standard Android media controls, including play/pause, next, previous, and repeat.

#### Multiple ROM Library

The Library screen lets you switch between multiple ROMs added from the GUI tool.
ROMs other than GBS Player ROMs can also be loaded.

#### Additional Convenience Features

See [Android Player features (Japanese)](docs/android-player.md) for details.

---

## Build Guide

### Requirements

- GBS files or GB/GBC ROM files
- Windows or a Windows-10-or-newer-compatible environment
- GBDK-2020
- Python 3
- GNU make
  - On Windows, `ezwinports.make` installed through `winget` is recommended.

To build the Android Player, you also need:

- Android Studio
  - Android SDK/NDK
  - CMake
- Android developer options enabled and a paired device

#### Clone the Repository

Clone this repository and move into the project root.

```powershell
git clone https://github.com/kleusbalut/gbs_player
cd gbs_player
```

#### Install Required Development Tools

Install GBDK-2020, Python 3, and GNU make.

Download GBDK-2020 from the official releases page and, if possible, place it at `C:/dev/gbdk`.

[GBDK-2020 Releases](https://github.com/gbdk-2020/gbdk-2020/releases/)

If you are using Windows 11 or newer, download `gbdk-win64.zip`.

> [!NOTE]
> The examples below assume GBDK is installed at `C:/dev/gbdk`.
> If you install it somewhere else, adjust the path accordingly.

Install Python 3:

```powershell
winget install Python.Python.3.14 --source winget
```

Then install make:

```powershell
winget install ezwinports.make --source winget
```

If the `make` command is not found after installation, reopen PowerShell.

#### Set Up Android Studio

To build the Android Player, install [Android Studio](https://developer.android.com/studio) and set up the Android SDK, NDK, and CMake.

> [!NOTE]
> If you do not need the Android Player, skip to [Run GBSPlayerTool](#run-gbsplayertool).

> [!NOTE]
> If you already have an Android development environment and your device is set up, skip to [Fetch SameBoy](#fetch-sameboy).

On Windows, install Android Studio from PowerShell:

```powershell
winget install Google.AndroidStudio --source winget
```

After installation, launch Android Studio once and complete the initial setup.
Choose `Standard` on the `Install Type` screen.

> [!NOTE]
> If you choose `Custom` or skip setup, open Android Studio with an empty project and install the following from `Tools > SDK Manager`:
>
> - Android SDK Platform 34
> - Android SDK Build-Tools
> - NDK (Side by side)
> - CMake 3.22.1

After setup, open `apps/android` in Android Studio and confirm that the project loads correctly.

#### Enable Android Developer Options and Pair a Device

Follow the Android documentation to enable developer options and connect or pair your device:

https://developer.android.com/studio/run/device

#### Fetch SameBoy

The Android Player requires SameBoy, the Game Boy emulator core. Install it with:

```powershell
python tools/fetch_sameboy.py
```

> [!TIP]
> At this point, you can also build from the command line.
> See [Build information](./docs/build.en.md) for command-line APK build instructions.

#### Run GBSPlayerTool

Install the Python dependencies once before first use.

```powershell
python -m pip install -r requirements.txt
```

and double-click `gbs_player_tool.py`.

<img src="images/2026-05-10 230857.png" height=300px>

GBS Player Tool can edit song names, song durations, playlists, title, author, and playback settings.

> [!TIP]
> Text shown on the ROM is limited to alphanumeric characters, some symbols, hiragana, and katakana.
> See the [supported character list (Japanese)](docs/usable-characters.md) for details.

After configuring your sources, confirm that the target Android device is selected and click `Build All and Install`.
If multiple sources are configured, the build may take some time.

You can also click `Build` to build only the selected source's GBS Player ROM.
After the build finishes, the output folder opens so you can use the generated files.

> [!NOTE]
> If no install target is found, check the device connection.

The GBS Player build is now complete.

Please report issues if you find any.

---

## Credits and Acknowledgements

- GBDK-2020: <https://github.com/gbdk-2020/gbdk-2020>
- SameBoy: <https://github.com/LIJI32/SameBoy>
  - Used as the embedded emulator in Android Player.
- Pokemon font: <https://nue2004.info/program/pkmn/>
  - Used for Japanese text rendering.
- BGB emulator: <https://bgb.bircd.org/>
  - Used for debugging.

## References

- pret disassembly projects: <https://pret.github.io/>
- RGBDS: <https://github.com/gbdev/rgbds>
- GF2MID: <https://github.com/turboboy215/GF2MID>
- gbsplay: <https://github.com/mmitch/gbsplay>
  - This project was inspired by gbsplay.

---

## Important Notice

Do not distribute ROMs generated by this tool, or data containing third-party copyrighted works, over the internet or through other channels.

The `MIT License` applies only to the project-specific source code. It does not apply to generated output produced by this program.
