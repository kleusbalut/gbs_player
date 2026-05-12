## Controls and Option Menu Reference

[Japanese version (Japanese)](usage.md)

### Song List Mode

<img src="../images/2026-05-10 234235.png" width=300px>

- `A`: Play / pause
- `B`: Stop
- `Up / Down`: Move cursor
- `Left / Right`: Move to the previous / next song
  - Only available during playback
- `SELECT`: Switch to playlist mode
  - Does nothing if the playlist is empty
- `START`: Open the option menu

Song list mode shows the full song list. If playback starts while the playlist is empty, automatic track advance follows this song order.

### Playlist Mode

<img src="../images/2026-05-10 234254.png" width=300px>

- `A`: Play / pause
  - Confirms the move while rearranging songs
- `B`: Stop
  - Cancels the move while rearranging songs
- `Up / Down`: Move cursor
- `Left / Right`: Move to the previous / next song
  - Only available during playback
- `SELECT`:
  - Short press: switch to song list mode
    - Cancels rearranging if a song is being moved
  - Long press: pick up / place a song
- `START`: Open the option menu

If playback starts in playlist mode, automatic track advance follows the playlist order. While rearranging, the picked-up song is inserted at the selected position.

### Option Menu

<img src="../images/2026-05-10 234307.png" width=300px>

- `Up / Down`: Select item
- `A / Left / Right`: Change the selected item's value
- `B`: Close the option menu

Options:

- `ADD PLAYLIST`: Add the selected song to the playlist
- `DEL PLAYLIST`: Remove the selected song from the playlist
- `Move`: Start rearranging songs; playlist mode only
- `Time`: Set the playback duration for each song
- `Fade`: Set the fade-out duration
  - Playback fades out smoothly over the selected duration.
- `Sil`: Set the silence detection duration
  - If silence is detected for this duration, the player advances to the next song regardless of the playback duration setting.
- `RPT`: Repeat mode (`---` / `ONE` / `ALL`)
- `Out`: Audio output mode (`STEREO` / `MONO`)

Playlist contents and settings are saved to SRAM, so they are retained on the next startup.
