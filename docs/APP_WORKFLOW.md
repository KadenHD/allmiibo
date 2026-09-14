# Application workflow

## Goal

Allmiibo Manager hides the BLE protocol, drive letters, and internal folders.
Users manage only their amiibo library.

## Primary flow

1. The application starts and automatically scans for an Allmiibo/Pixl.js in
   **Bluetooth Transmission** mode.
2. After connecting, it keeps the BLE session open and displays the remote
   library as a folder tree.
3. Users can add `.bin` files, upload a folder, create, rename, or delete an
   item, and refresh the library.
4. Automatic import accepts the ZIP downloaded from the Google Drive folder
   linked by the application. It extracts the archive faithfully into a Windows
   temporary directory, synchronizes it, and deletes it automatically.
5. During import, identical content is skipped, different content is
   overwritten, and new content is added. Remote files missing from the ZIP are
   preserved.
6. The connection is monitored while the application remains open. An error
   returns to a reconnection screen without exposing protocol details. Attempts
   resume automatically with delays from 4 to 30 seconds.
7. The header shows available storage recalculated after each refresh or
   operation. Drag-and-drop selects the folder under the pointer and displays
   the destination in the activity area.
8. The first column can select multiple files and folders. Its header checkbox
   selects or clears every allowed item, the delete button displays the count,
   and one confirmation summarizes the targets. Only the **Name** column carries
   child indentation, keeping every checkbox aligned and visible.
9. The help banner states that Kirby Air Riders requires Pixl.js 2.16+ and links
   directly to the DFU tool and firmware releases.
10. The **amiibo** root is visible and selectable. Clicking empty tree space also
    selects it, so later uploads never silently reuse the previous destination.
11. At narrow widths, a **More** button follows the remaining visible actions
    and contains only the commands that do not fit.
12. The window can be closed immediately from the initial screen. An active BLE
    scan is cancelled without waiting for its timeout or the next automatic
    retry.
13. The first inventory creates an in-memory index. Every successful mutation
    updates it locally and sends only additions, changes, and removals to the
    displayed folder tree. Only **Refresh** invalidates the index, scans every
    folder again, and rebuilds the complete display.
14. Long operations report their stages in **Details** and the compact status.
    A heartbeat every five seconds confirms that communication continues during
    an individual slow BLE request. Transfer progress replaces the heartbeat as
    soon as file events begin. The final duration is appended to the log.
15. The Windows taskbar reflects indeterminate work, progress, success, and
    failure. A sound and subtle notification announce completed ZIP imports,
    multi-file uploads, and group deletions.

## Safety rules

- Every visible operation is restricted to the `amiibo` library.
- The library root cannot be deleted.
- The `fav` and `data` folders cannot be deleted or renamed. Any parent folder
  containing them is also excluded from recursive deletion.
- Manual deletion always requires confirmation.
- One directory cannot contain two folders with the same case-insensitive name.
- Renaming an amiibo never makes its `.bin` extension editable.
- File replacement uses a verified temporary copy and restores the original if
  the operation fails.
- The application retains no ZIP archive or imported file.
- Names are never rewritten: no aliases, prefix removal, or automatic
  shortening. A manual path that violates protocol limits is rejected before
  upload.
- Import details separate ZIP preparation from BLE synchronization. Deletion
  details list targets and file/folder totals.
- The in-memory index is cleared on disconnection. Changes made with another
  tool during the session become visible through **Refresh**, which rebuilds the
  index from the device.

## Open decision

ZIP import currently performs a merged update and preserves files found only on
the device. A future exact-mirror mode could delete them, but it must remain a
separate operation with a strong confirmation.
