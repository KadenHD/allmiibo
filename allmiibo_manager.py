"""Persistent high-level library management for an Allmiibo/Pixl.js device."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from allmiibo_ble import (
    AllmiiboError,
    BleakNusTransport,
    DirectoryEntry,
    PixlVfsClient,
    StatusCallback,
    SyncReport,
    _ensure_remote_root,
    _replace_file_safely,
    _walk_remote,
    choose_remote_root,
    join_device_path,
    validate_device_path,
)
from format_data import ExtractionReport, extract_archive


TransferProgress = Callable[[int, int, str, str], None]
PROTECTED_DIRECTORIES = frozenset({"fav", "data"})


@dataclass(frozen=True)
class RemoteItem:
    relative_path: str
    name: str
    size: int
    is_directory: bool


@dataclass(frozen=True)
class ConnectionInfo:
    device_name: str
    firmware_version: str
    total_size: int
    free_size: int


@dataclass
class TransferReport:
    created: int = 0
    overwritten: int = 0
    identical: int = 0
    folders_created: int = 0


@dataclass(frozen=True)
class ImportReport:
    extraction: ExtractionReport
    synchronization: SyncReport


@dataclass(frozen=True)
class DeleteReport:
    requested: tuple[str, ...]
    removed_files: int
    removed_folders: int

    @property
    def total(self) -> int:
        return self.removed_files + self.removed_folders


def _clean_relative(value: str | PurePosixPath) -> PurePosixPath:
    text = str(value).replace("\\", "/").strip("/")
    if not text:
        return PurePosixPath()
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Invalid relative path: {value!r}")
    return path


def is_protected_directory_path(relative_path: str | PurePosixPath) -> bool:
    """Return whether a directory name is reserved by the Allmiibo firmware."""

    path = (
        relative_path
        if isinstance(relative_path, PurePosixPath)
        else _clean_relative(relative_path)
    )
    return bool(path.parts) and path.name.casefold() in PROTECTED_DIRECTORIES


def _display_name(value: str) -> str:
    return value.strip().strip(" .")


class AllmiiboManager:
    """Own one BLE connection and expose safe operations on the amiibo library."""

    def __init__(self, *, scan_timeout: float = 15.0) -> None:
        self.scan_timeout = scan_timeout
        self.transport: BleakNusTransport | None = None
        self.client: PixlVfsClient | None = None
        self.remote_root: str | None = None
        self.info: ConnectionInfo | None = None
        self._entries: dict[PurePosixPath, DirectoryEntry] | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None and self.remote_root is not None

    def _require_client(self) -> tuple[PixlVfsClient, str]:
        if self.client is None or self.remote_root is None:
            raise AllmiiboError("The Allmiibo is not connected.")
        return self.client, self.remote_root

    async def connect(self) -> ConnectionInfo:
        await self.close()
        transport = BleakNusTransport()
        try:
            device_name = await transport.connect(scan_timeout=self.scan_timeout)
            client = PixlVfsClient(transport)
            firmware_version = await client.get_version()
            drives = await client.get_drives()
            remote_root = choose_remote_root(drives, None, "amiibo")
            await _ensure_remote_root(client, remote_root, dry_run=False)
        except Exception:
            await transport.close()
            raise

        selected_drive = next(
            drive for drive in drives if remote_root.startswith(f"{drive.label}:/")
        )
        self.transport = transport
        self.client = client
        self.remote_root = remote_root
        self.info = ConnectionInfo(
            device_name=device_name,
            firmware_version=firmware_version,
            total_size=selected_drive.total_size,
            free_size=selected_drive.free_size,
        )
        self._entries = None
        return self.info

    async def ping(self) -> None:
        client, _ = self._require_client()
        await client.get_version()

    async def refresh_info(self) -> ConnectionInfo:
        client, remote_root = self._require_client()
        if self.info is None:
            raise AllmiiboError("Allmiibo device information is unavailable.")
        drives = await client.get_drives()
        selected_drive = next(
            (
                drive
                for drive in drives
                if remote_root.startswith(f"{drive.label}:/")
            ),
            None,
        )
        if selected_drive is None:
            raise AllmiiboError("Allmiibo storage is unavailable.")
        self.info = ConnectionInfo(
            device_name=self.info.device_name,
            firmware_version=self.info.firmware_version,
            total_size=selected_drive.total_size,
            free_size=selected_drive.free_size,
        )
        return self.info

    async def close(self) -> None:
        transport = self.transport
        self.transport = None
        self.client = None
        self.remote_root = None
        self.info = None
        self._entries = None
        if transport is not None:
            await transport.close()

    async def _ensure_entries(
        self,
        *,
        force_refresh: bool = False,
        status_callback: StatusCallback | None = None,
    ) -> dict[PurePosixPath, DirectoryEntry]:
        client, remote_root = self._require_client()
        if self._entries is None or force_refresh:
            if status_callback is not None:
                status_callback("Starting a full library scan…")
            self._entries = await _walk_remote(
                client,
                remote_root,
                status_callback=status_callback,
            )
            if status_callback is not None:
                folders = sum(entry.is_directory for entry in self._entries.values())
                files = len(self._entries) - folders
                status_callback(
                    f"Index complete: {files} amiibo(s), {folders} folder(s)."
                )
        return self._entries

    async def list_library(
        self,
        *,
        force_refresh: bool = False,
        status_callback: StatusCallback | None = None,
    ) -> list[RemoteItem]:
        entries = await self._ensure_entries(
            force_refresh=force_refresh,
            status_callback=status_callback,
        )
        result = [
            RemoteItem(
                relative_path=relative.as_posix(),
                name=entry.name,
                size=entry.size,
                is_directory=entry.is_directory,
            )
            for relative, entry in entries.items()
        ]
        return sorted(
            result,
            key=lambda item: (
                tuple(part.casefold() for part in PurePosixPath(item.relative_path).parts),
                not item.is_directory,
            ),
        )

    async def create_folder(
        self,
        parent: str,
        name: str,
        *,
        status_callback: StatusCallback | None = None,
    ) -> str:
        client, remote_root = self._require_client()
        if status_callback is not None:
            status_callback("Validating the new folder against the local index…")
        clean_name = _display_name(name)
        if not clean_name or "/" in clean_name or "\\" in clean_name:
            raise ValueError("The folder name is invalid.")
        parent_relative = _clean_relative(parent)
        entries = await self._ensure_entries(status_callback=status_callback)
        if parent_relative.parts:
            parent_entry = entries.get(parent_relative)
            if parent_entry is None or not parent_entry.is_directory:
                raise FileNotFoundError(
                    f"Parent folder not found: {parent_relative.as_posix()}"
                )
        relative = parent_relative / clean_name
        conflict = next(
            (
                path
                for path in entries
                if path.parent == relative.parent
                and path.name.casefold() == clean_name.casefold()
            ),
            None,
        )
        if conflict is not None:
            location = relative.parent.as_posix()
            location = "Library" if location == "." else location
            kind = "folder" if entries[conflict].is_directory else "file"
            raise FileExistsError(
                f'A {kind} named "{conflict.name}" already exists in {location}.'
            )
        destination = join_device_path(remote_root, relative)
        validate_device_path(destination)
        if status_callback is not None:
            status_callback(f"Creating on the Allmiibo: {relative.as_posix()}")
        await client.create_directory(destination)
        entries[relative] = DirectoryEntry(clean_name, 0, True)
        if status_callback is not None:
            status_callback("Local index updated without another BLE scan.")
        return relative.as_posix()

    async def rename(
        self,
        relative_path: str,
        new_name: str,
        *,
        status_callback: StatusCallback | None = None,
    ) -> str:
        client, remote_root = self._require_client()
        source_relative = _clean_relative(relative_path)
        if status_callback is not None:
            status_callback("Validating the rename against the local index…")
        entries = await self._ensure_entries(status_callback=status_callback)
        source_entry = entries.get(source_relative)
        if source_entry is None:
            raise FileNotFoundError(
                f"Item not found: {source_relative.as_posix()}"
            )
        if source_entry.is_directory and is_protected_directory_path(source_relative):
            raise ValueError(
                "The fav and data folders are protected and cannot be renamed."
            )
        clean_name = _display_name(new_name)
        if (
            not source_relative.parts
            or not clean_name
            or "/" in clean_name
            or "\\" in clean_name
        ):
            raise ValueError("The new name is invalid.")
        if source_relative.suffix.lower() == ".bin":
            if clean_name.lower().endswith(".bin"):
                clean_name = clean_name[:-4]
            clean_name = _display_name(clean_name)
            if not clean_name:
                raise ValueError("The file name is invalid.")
            clean_name += ".bin"
        destination_relative = source_relative.parent / clean_name
        conflict = next(
            (
                path
                for path in entries
                if path != source_relative
                and path.parent == destination_relative.parent
                and path.name.casefold() == clean_name.casefold()
            ),
            None,
        )
        if conflict is not None:
            raise FileExistsError(
                f'An item named "{conflict.name}" already exists in this folder.'
            )
        if destination_relative == source_relative:
            return source_relative.as_posix()
        source = join_device_path(remote_root, source_relative)
        destination = join_device_path(remote_root, destination_relative)
        validate_device_path(destination)
        if status_callback is not None:
            status_callback(
                f"Renaming on the Allmiibo: {source_relative.as_posix()} → "
                f"{destination_relative.as_posix()}"
            )
        await client.rename(source, destination)
        moved: dict[PurePosixPath, DirectoryEntry] = {}
        affected = [
            path
            for path in entries
            if path == source_relative or source_relative in path.parents
        ]
        for path in affected:
            entry = entries.pop(path)
            if path == source_relative:
                moved[destination_relative] = DirectoryEntry(
                    clean_name, entry.size, entry.is_directory
                )
            else:
                moved[destination_relative / path.relative_to(source_relative)] = entry
        entries.update(moved)
        if status_callback is not None:
            status_callback(
                f"Local index updated: {len(moved)} item(s) moved."
            )
        return destination_relative.as_posix()

    async def delete(
        self,
        relative_path: str,
        *,
        status_callback: StatusCallback | None = None,
    ) -> DeleteReport:
        return await self.delete_many(
            [relative_path], status_callback=status_callback
        )

    async def delete_many(
        self,
        relative_paths: Iterable[str],
        *,
        status_callback: StatusCallback | None = None,
    ) -> DeleteReport:
        client, remote_root = self._require_client()
        requested = {_clean_relative(path) for path in relative_paths}
        if not requested:
            raise ValueError("No item was selected.")
        if any(not relative.parts for relative in requested):
            raise ValueError("The library root cannot be deleted.")

        if status_callback is not None:
            status_callback("Resolving items to delete from the local index…")
        entries = await self._ensure_entries(status_callback=status_callback)
        missing = [relative for relative in requested if relative not in entries]
        if missing:
            raise FileNotFoundError(f"Item not found: {missing[0].as_posix()}")

        targets = {
            relative
            for relative in requested
            if not any(parent in requested for parent in relative.parents)
        }
        protected = {
            path
            for path, entry in entries.items()
            if entry.is_directory and is_protected_directory_path(path)
        }
        blocked = {
            target
            for target in targets
            if any(folder == target or target in folder.parents for folder in protected)
        }
        if blocked:
            names = ", ".join(sorted(path.as_posix() for path in blocked))
            raise ValueError(
                f"Deletion is forbidden for {names}: the fav and data folders "
                "must always be preserved."
            )

        descendants = [
            path
            for path in entries
            if any(path == target or target in path.parents for target in targets)
        ]
        removed_folders = sum(entries[path].is_directory for path in descendants)
        removed_files = len(descendants) - removed_folders
        descendants.sort(key=lambda path: len(path.parts), reverse=True)
        total = len(descendants)
        for position, path in enumerate(descendants, start=1):
            await client.remove(join_device_path(remote_root, path))
            entries.pop(path, None)
            if status_callback is not None and (
                position == 1 or position % 25 == 0 or position == total
            ):
                status_callback(
                    f"Deleting from the Allmiibo: {position}/{total} — "
                    f"{path.as_posix()}"
                )
        if status_callback is not None:
            status_callback("Local index cleaned without another BLE scan.")
        return DeleteReport(
            requested=tuple(sorted(path.as_posix() for path in targets)),
            removed_files=removed_files,
            removed_folders=removed_folders,
        )

    @staticmethod
    def _collect_sources(
        sources: Iterable[Path],
        target_directory: PurePosixPath,
    ) -> list[tuple[Path, PurePosixPath]]:
        files: list[tuple[Path, PurePosixPath]] = []

        def destination_for(source: Path, directories: list[str]) -> PurePosixPath:
            return target_directory.joinpath(*directories, source.name)

        for source in sources:
            source = source.resolve()
            if source.is_file():
                if source.suffix.lower() != ".bin":
                    raise ValueError(f"Only .bin files are accepted: {source.name}")
                files.append((source, destination_for(source, [])))
                continue
            if not source.is_dir():
                raise FileNotFoundError(f"Source not found: {source}")
            for path in sorted(source.rglob("*"), key=lambda item: str(item).casefold()):
                if path.is_file() and path.suffix.lower() == ".bin":
                    relative = path.relative_to(source)
                    directories = [
                        source.name,
                        *relative.parts[:-1],
                    ]
                    destination = destination_for(path, directories)
                    files.append((path, destination))
        if not files:
            raise ValueError("No .bin file was found in the selection.")
        return files

    async def upload(
        self,
        sources: Iterable[Path],
        target_directory: str = "",
        *,
        progress_callback: TransferProgress | None = None,
        status_callback: StatusCallback | None = None,
    ) -> TransferReport:
        client, remote_root = self._require_client()
        if status_callback is not None:
            status_callback("Scanning the selected local files…")
        target = _clean_relative(target_directory)
        files = self._collect_sources(sources, target)
        current_entries = await self._ensure_entries(status_callback=status_callback)
        if status_callback is not None:
            status_callback(
                f"{len(files)} file(s) ready; comparing against the local index…"
            )
        report = TransferReport()

        directories: set[PurePosixPath] = set()
        for _, relative in files:
            directories.update(
                PurePosixPath(*relative.parts[:index])
                for index in range(1, len(relative.parts))
            )
            validate_device_path(join_device_path(remote_root, relative))

        for directory in sorted(directories, key=lambda path: (len(path.parts), str(path))):
            entry = current_entries.get(directory)
            if entry is not None and not entry.is_directory:
                raise AllmiiboError(
                    f"A file blocks creation of folder {directory.as_posix()}."
                )
            if entry is None:
                await client.create_directory(join_device_path(remote_root, directory))
                current_entries[directory] = DirectoryEntry(directory.name, 0, True)
                report.folders_created += 1

        total = len(files)
        for index, (source, relative) in enumerate(files, start=1):
            destination = join_device_path(remote_root, relative)
            data = source.read_bytes()
            existing = current_entries.get(relative)
            if existing is not None and existing.is_directory:
                raise AllmiiboError(
                    f"A folder blocks file {relative.as_posix()}."
                )
            if (
                existing is not None
                and existing.size == len(data)
                and await client.read_file(destination) == data
            ):
                report.identical += 1
                action = "identical"
            else:
                await _replace_file_safely(
                    client,
                    destination,
                    data,
                    destination_exists=existing is not None,
                )
                if existing is None:
                    report.created += 1
                    action = "added"
                else:
                    report.overwritten += 1
                    action = "overwritten"
            current_entries[relative] = DirectoryEntry(relative.name, len(data), False)
            if progress_callback is not None:
                progress_callback(index, total, action, relative.as_posix())
        if status_callback is not None:
            status_callback("Local index synchronized with completed transfers.")
        return report

    async def import_archive(
        self,
        archive_path: Path,
        *,
        progress_callback: TransferProgress | None = None,
        status_callback: StatusCallback | None = None,
    ) -> ImportReport:
        client, remote_root = self._require_client()
        current_entries = await self._ensure_entries(status_callback=status_callback)
        with tempfile.TemporaryDirectory(prefix="Allmiibo-Import-") as temporary:
            output = Path(temporary) / "library"
            if status_callback is not None:
                status_callback("Opening and validating the ZIP archive…")

            def extraction_progress(
                current: int, total: int, action: str, path: Path
            ) -> None:
                if status_callback is not None and (
                    current == 1 or current % 50 == 0 or current == total
                ):
                    status_callback(
                        f"Preparing ZIP: {current}/{total} — "
                        f"{action} — {path.name}"
                    )

            extraction = extract_archive(
                archive_path,
                output,
                conflict="overwrite",
                progress_callback=extraction_progress,
            )
            if status_callback is not None:
                status_callback(
                    f"ZIP prepared: {extraction.extracted} file(s) extracted."
                )
                status_callback(
                    "Comparing ZIP files against the device index in memory…"
                )
            synchronization = await self._sync_import(
                client,
                output,
                remote_root,
                current_entries=current_entries,
                progress_callback=progress_callback,
            )
            if status_callback is not None:
                status_callback("Cleaning temporary import data…")
        return ImportReport(extraction, synchronization)

    @staticmethod
    async def _sync_import(
        client: PixlVfsClient,
        output: Path,
        remote_root: str,
        *,
        current_entries: dict[PurePosixPath, DirectoryEntry],
        progress_callback: TransferProgress | None,
    ) -> SyncReport:
        from allmiibo_ble import sync_directory

        def relative_progress(
            current: int, total: int, action: str, device_path: str
        ) -> None:
            if progress_callback is None:
                return
            prefix = remote_root.rstrip("/") + "/"
            relative_path = (
                device_path[len(prefix) :]
                if device_path.startswith(prefix)
                else PurePosixPath(device_path).name
            )
            progress_callback(current, total, action, relative_path)

        return await sync_directory(
            client,
            output,
            remote_root,
            progress_callback=relative_progress,
            remote_entries=current_entries,
        )
