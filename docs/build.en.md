# Build Information

[Japanese version (Japanese)](build.md)

## Building GBS Player

> [!NOTE]
> This page assumes that the required build environment is already set up.

### Building the Player ROM

#### Prepare a GBS, GB, or GBC File

Place the source file somewhere such as `samples/gbs/`. If you want to use a song name file, place `<filename>.names.txt` in the same directory as the source file.

See [Song name / duration list format (Japanese)](songlist-format.md) for the file format.

#### Build

Run the following command:

```powershell
make GBDK=C:/dev/gbdk GBS=samples/gbs/music.gbs
```

> [!NOTE]
> If GBDK-2020 is installed somewhere else, change the `GBDK=` path.

The output is written to `build/gbs_player.gbc`.

## Building Android Player from the Command Line

### Android Build

#### Fetch SameBoy

Run the following command in PowerShell to fetch SameBoy, the Game Boy emulator core:

```powershell
python tools/fetch_sameboy.py
```

#### Generate Player Metadata

Run the following command to sync the ROM into the Android assets and generate metadata such as song names:

```bash
make android-assets GBDK=C:/dev/gbdk GBS=samples/gbs/music.gbs
```

#### Build the APK

```powershell
cd apps/android
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:Path="$env:JAVA_HOME\bin;$env:Path"
.\gradlew.bat assembleDebug
```

The APK is written to:

```text
apps/android/app/build/outputs/apk/debug/app-debug.apk
```

### About `make clean`

```bash
make clean
```

In this build system, `make clean` sends generated ROMs and intermediate files to the Windows Recycle Bin.

> [!NOTE]
> If the Recycle Bin API is unavailable, files are moved to `.trash/` inside the project instead of being permanently deleted.
> In normal rebuilds, generated files are overwritten as needed, so first-time users usually do not need to run `make clean`.

### Changing Supported Font Characters

Normal ROM builds use the generated `src/player/jp_font.h`, so regenerating the font is not required.
If you need to change supported Japanese characters or regenerate font tiles yourself, run the following in PowerShell:

```powershell
python -m pip install Pillow fonttools
python tools/fetch_pkmnfont.py
python tools/gen_jp_font.py
```

The font is placed under `assets/fonts/pkmnfont/`.
