# Allmiibo Manager

A Windows application for managing an Allmiibo/Pixl.js library directly over
Bluetooth without exposing the device drives or internal folders.

## Usage

1. Put the Allmiibo in **Bluetooth Transmission** mode.
2. Start `AllmiiboManager.exe`; scanning and connection are automatic.
3. Manage amiibos from the folder tree displayed by the application.

The BLE connection stays open while the application is running. If it is lost,
the connection screen explains what to check and retries automatically with a
progressive delay. The button also starts an immediate retry.

### Add your own amiibos

Use **Add files** to select one or more `.bin` files, or **Add folder** to
preserve an existing organization. Files and folders can also be dropped
directly onto the folder tree.

File and folder names are preserved exactly. The application does not create
aliases or shortened names. If a manual upload exceeds a device protocol limit,
the upload stops with an explicit error instead of silently changing the name.

### Update from the shared library

Open the [amiibo Google Drive folder](https://drive.google.com/drive/folders/1fNo0qv-6GnMwNWXwZ6WLZI5LQzH-jX9f),
download the folder as a ZIP archive, then use **Import ZIP** in the application.
Names in this archive are already final and are preserved without changes.

After downloading it, click **Import ZIP** or drop the archive into the
application. The update follows these rules:

- same content: skip the file;
- different content: overwrite the file safely;
- new file: add the file;
- personal file missing from the ZIP: preserve the file.

The archive is prepared in the Windows temporary directory, then temporary data
is deleted automatically. The user never needs to manage a local `data/` folder.

### Pixl.js firmware

**Kirby Air Riders requires Pixl.js firmware 2.16 or later.** Release 2.16.0
adds support for the V3 amiibos used by the game.

- [Update with DFU](https://thegecko.github.io/web-bluetooth-dfu)
- [Download Pixl.js firmware releases](https://github.com/solosky/pixl.js/releases)

### Manage the folder tree

The action bar and context menu let you:

- create a folder;
- rename a file or folder while keeping the `.bin` extension locked for amiibos;
- select multiple files and folders in the first column, or use the header
  checkbox to select every deletable item, then delete them after one
  confirmation;
- delete the selected file or folder;
- refresh the real device state.

Two folders cannot have the same case-insensitive name in one parent directory.
The same name remains valid in different directories.

The checkboxes for `fav`, `data`, and their parent folders remain visible but
disabled. These folders cannot be selected for deletion or deleted, and `fav`
and `data` cannot be renamed. Tree indentation is limited to the **Name** column,
so every checkbox stays aligned and accessible at any depth.

The **amiibo** root is displayed as the first folder and can be selected as an
upload destination. Clicking empty space selects it and clears the previous
destination.

When horizontal space is limited, actions that no longer fit move into a
**More** button immediately after the remaining visible actions. Its arrow shows
whether the menu is open. The **Details** panel keeps deletion targets and
file/folder totals, as well as separate ZIP extraction and synchronization
summaries.

### Performance with a large library

A full BLE scan runs once at connection time and then only when the user clicks
**Refresh**. Folder creation, renaming, deletion, upload, and import update an
in-memory index, so they no longer scan 1,000+ amiibos after every change. The UI
also applies only added, changed, and removed items instead of rebuilding the
complete folder tree after a mutation.

**Refresh** deliberately verifies the complete device state and may therefore
take several minutes. During the scan, the status area and **Details** show the
storage step, current folder, indexed item count, and an activity heartbeat
every five seconds. Use it after making changes outside the application or when
you need to rebuild the displayed state from the device.

During a transfer, detailed progress replaces the periodic heartbeat. The total
duration appears on completion, the Windows taskbar tracks progress, and a sound
with a notification announces completed ZIP imports, multi-file uploads, and
group deletions.

A drag-and-drop operation targets the folder under the pointer and shows that
destination in the activity area. The header also reports available storage
after each refresh.

Every operation is restricted to the amiibo library. Device system data is not
exposed by the interface.

## Development

Requirements: Python 3.10 or later and Windows 10 or later for BLE support.

```powershell
python -m pip install -r ./requirements-gui.txt
python ./allmiibo_gui.py
```

Run tests:

```powershell
python -m unittest discover -v
```

Build the executable:

```powershell
./build.ps1
```

The result is created at `dist/AllmiiboManager.exe`. PySide6 6.8.3 is pinned
because newer tested versions caused a Qt DLL conflict in the Windows
PyInstaller package.

## GitHub releases

The `.github/workflows/release.yml` workflow runs the tests, builds the `.exe`,
smoke-tests it, and generates a SHA-256 checksum.

```powershell
git tag v2.0.0
git push origin v2.0.0
```

Any `v*` tag automatically creates a GitHub Release. The executable is not code
signed, so Windows SmartScreen may show a warning until a code-signing
certificate is configured.

## Command-line tools

The graphical interface is the primary workflow. Historical scripts remain
available for automation:

```powershell
# Extract an archive faithfully into data/
python ./format_data.py ./amiibo-library.zip

# Prepare and then synchronize
python ./format_data.py ./amiibo-library.zip --sync

# Synchronize an already prepared folder
python ./format_data.py --sync
```

Preparation preserves the exact names and folder tree from the ZIP, except for
an optional common root folder. It applies no aliases, prefix removal, or name
shortening.

## Documentation

- [Application workflow](docs/APP_WORKFLOW.md)
- [Development status](docs/DEVELOPMENT_STATUS.md)
- [v2.0.0 release notes](docs/RELEASE_NOTES_v2.0.0.md)
- [Pixl.js BLE protocol](https://github.com/solosky/pixl.js/blob/main/docs/en/05%2B1-ble_protocol.md)
