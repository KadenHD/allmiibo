# Allmiibo Manager v2.0.0

Allmiibo Manager v2 replaces the preparation-first workflow with a persistent
Bluetooth library manager for Windows.

## Highlights

- Connects to an Allmiibo/Pixl.js device and keeps the BLE session active.
- Displays the complete remote library as a manageable folder tree.
- Adds, renames, and deletes `.bin` files and folders directly on the device.
- Supports multi-selection and protected `fav` and `data` folders.
- Imports the shared Google Drive ZIP with skip-identical, overwrite-different,
  and add-new behavior while preserving personal files.
- Preserves the final names supplied by the shared library without aliases or
  automatic shortening.
- Uses an in-memory device index and incremental UI updates after mutations,
  avoiding a full BLE scan after every operation.
- Reports detailed progressive status, transfer progress, elapsed time,
  Windows taskbar progress, and completion notifications.
- Adds responsive actions, a selectable `amiibo` root, drag and drop, and the
  new application icon.
- Allows an active BLE scan to be cancelled immediately when the app closes.
- Converts the complete repository and application interface to English.

## Requirements

- Windows 10 or later with Bluetooth Low Energy support.
- An Allmiibo/Pixl.js device in Bluetooth Transmission mode.
- Pixl.js firmware 2.16 or later for Kirby Air Riders amiibos.

## Installation

Download `AllmiiboManager.exe` from the GitHub release and run it directly. No
installation is required. The executable is not code signed, so Windows
SmartScreen may show an unknown-publisher warning.

The accompanying `AllmiiboManager.exe.sha256` file can be used to verify that
the executable was downloaded without corruption.

## Known limitation

The automated suite covers the BLE protocol through a simulated device. Final
connection-lifetime validation still requires a physical Allmiibo.
