# Development status

Last updated: 2026-09-15

## Current target

Publish the licensing and responsible-use update as v2.0.1.

## Completed before this redesign

- Pixl.js BLE protocol: file reads/writes, folders, deletion, and renaming.
- Safe synchronization: skip identical files, overwrite different files, and
  add new files.
- Allmiibo path-limit validation before transfer.
- Windows PyInstaller build and GitHub Release workflow.

## Redesign progress

- [x] Define the new user workflow.
- [x] Add a business layer for a persistent connection.
- [x] Use Windows temporary storage and clean it automatically.
- [x] Replace the interface with a connection screen and remote explorer.
- [x] Add file/folder actions and drag-and-drop.
- [x] Add guided ZIP import with a link to the Google Drive folder.
- [x] Preserve Drive names without aliases or automatic shortening.
- [x] Add DFU/release links and the Pixl.js 2.16+ requirement for Kirby Air Riders.
- [x] Add connection, error, and progress states.
- [x] Add automatic reconnection with progressive delays.
- [x] Make the drag-and-drop destination explicit and deterministic.
- [x] Display available storage after each refresh.
- [x] Add checkbox selection and grouped item deletion.
- [x] Fix global-checkbox interaction and keep indentation in the Name column.
- [x] Extend deletion checkboxes to `.bin` files.
- [x] Make an empty-space click return explicitly to the Library root.
- [x] Reject duplicate sibling folder names and lock the `.bin` extension.
- [x] Replace native overflow with a responsive inline `More` button.
- [x] Add detailed deletion and ZIP import summaries to the log.
- [x] Apply an amiibo icon to the window and Windows package.
- [x] Present initial connection as a scan of the existing folder structure.
- [x] Allow closing during BLE scanning and cancel it cleanly.
- [x] Maintain an in-memory folder index after every mutation.
- [x] Remove duplicate BLE scans after creation, rename, deletion, and upload.
- [x] Reuse the index during ZIP import instead of scanning the device again.
- [x] Break long operations into stages with a heartbeat every five seconds.
- [x] Display a selectable `amiibo` root as an upload destination.
- [x] Update the folder tree by delta instead of rebuilding it after mutations.
- [x] Add final duration, Windows taskbar progress, and batch notifications.
- [x] Space action icons and make the `More` arrow reversible.
- [x] Use a dark green ZIP import action and replace the icon with the supplied asset.
- [x] Protect `fav`, `data`, and their parents from deletion.
- [x] Complete business-logic and interface tests.
- [x] Rebuild and verify the Windows executable.
- [x] Update README.md and DESIGN.md.
- [x] Convert every tracked code, UI, test, comment, and documentation string to English.
- [x] Prepare v2.0.0 release notes and release metadata.
- [x] Add the MIT project license and third-party open-source notices.
- [x] Add a responsible-use notice for user-provided amiibo data.
- [x] Include legal notices in local and GitHub release packages.
- [x] Prepare the v2.0.1 licensing release.

## Validation status

- 47 unit tests pass, including the legal-package and repository English-only
  guards, folder
  conflicts, `.bin` extension locking,
  root selection, the `More` menu, global selection, protected Qt checkboxes,
  immediate cancellation of an active BLE scan, and the absence of new BLE
  scans after ordinary mutations.
- English Qt previews at 1080×720 and 760×560 were reviewed for the library and
  connection screens.
- The Impeccable detector reported no mechanical issue.
- Native previews of multi-selection and protected folders were reviewed.
- PyInstaller build succeeded with PySide6 6.8.3.
- Executable self-test exits with code `0`.
- The local v2.0.0 release candidate is 42,732,171 bytes
  with SHA-256
  `20D816F7670D756AC1DAB6302E8C83ED6F0CDA8B29707C8A56A41E430459B636`.
- Final hardware testing is still required to confirm connection lifetime on a
  real Allmiibo.

## Expected validation

- Unit tests with a simulated VFS client.
- Offscreen PySide6 smoke test.
- `.exe` build with PySide6 6.8.3 and executable self-test.
- Final hardware test with a connected physical Allmiibo.
