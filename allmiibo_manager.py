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
        raise ValueError(f"Chemin relatif invalide : {value!r}")
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

    @property
    def connected(self) -> bool:
        return self.client is not None and self.remote_root is not None

    def _require_client(self) -> tuple[PixlVfsClient, str]:
        if self.client is None or self.remote_root is None:
            raise AllmiiboError("L’Allmiibo n’est pas connecté.")
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
        return self.info

    async def ping(self) -> None:
        client, _ = self._require_client()
        await client.get_version()

    async def refresh_info(self) -> ConnectionInfo:
        client, remote_root = self._require_client()
        if self.info is None:
            raise AllmiiboError("Les informations de l’Allmiibo sont indisponibles.")
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
            raise AllmiiboError("Le stockage de l’Allmiibo est indisponible.")
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
        if transport is not None:
            await transport.close()

    async def list_library(self) -> list[RemoteItem]:
        client, remote_root = self._require_client()
        entries = await _walk_remote(client, remote_root)
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

    async def create_folder(self, parent: str, name: str) -> str:
        client, remote_root = self._require_client()
        clean_name = _display_name(name)
        if not clean_name or "/" in clean_name or "\\" in clean_name:
            raise ValueError("Le nom du dossier est invalide.")
        relative = _clean_relative(parent) / clean_name
        entries = await _walk_remote(client, remote_root)
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
            location = "Bibliothèque" if location == "." else location
            kind = "dossier" if entries[conflict].is_directory else "fichier"
            raise FileExistsError(
                f"Un {kind} nommé « {conflict.name} » existe déjà dans {location}."
            )
        destination = join_device_path(remote_root, relative)
        validate_device_path(destination)
        await client.create_directory(destination)
        return relative.as_posix()

    async def rename(self, relative_path: str, new_name: str) -> str:
        client, remote_root = self._require_client()
        source_relative = _clean_relative(relative_path)
        entries = await _walk_remote(client, remote_root)
        source_entry = entries.get(source_relative)
        if source_entry is None:
            raise FileNotFoundError(
                f"Élément introuvable : {source_relative.as_posix()}"
            )
        if source_entry.is_directory and is_protected_directory_path(source_relative):
            raise ValueError(
                "Les dossiers fav et data sont protégés et ne peuvent pas être renommés."
            )
        clean_name = _display_name(new_name)
        if (
            not source_relative.parts
            or not clean_name
            or "/" in clean_name
            or "\\" in clean_name
        ):
            raise ValueError("Le nouveau nom est invalide.")
        if source_relative.suffix.lower() == ".bin":
            if clean_name.lower().endswith(".bin"):
                clean_name = clean_name[:-4]
            clean_name = _display_name(clean_name)
            if not clean_name:
                raise ValueError("Le nom du fichier est invalide.")
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
                f"Un élément nommé « {conflict.name} » existe déjà dans ce dossier."
            )
        if destination_relative == source_relative:
            return source_relative.as_posix()
        source = join_device_path(remote_root, source_relative)
        destination = join_device_path(remote_root, destination_relative)
        validate_device_path(destination)
        await client.rename(source, destination)
        return destination_relative.as_posix()

    async def delete(self, relative_path: str) -> DeleteReport:
        return await self.delete_many([relative_path])

    async def delete_many(self, relative_paths: Iterable[str]) -> DeleteReport:
        client, remote_root = self._require_client()
        requested = {_clean_relative(path) for path in relative_paths}
        if not requested:
            raise ValueError("Aucun élément n’a été sélectionné.")
        if any(not relative.parts for relative in requested):
            raise ValueError("La racine de la bibliothèque ne peut pas être supprimée.")

        entries = await _walk_remote(client, remote_root)
        missing = [relative for relative in requested if relative not in entries]
        if missing:
            raise FileNotFoundError(f"Élément introuvable : {missing[0].as_posix()}")

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
                f"Suppression interdite pour {names} : les dossiers fav et data "
                "doivent toujours être conservés."
            )

        descendants = [
            path
            for path in entries
            if any(path == target or target in path.parents for target in targets)
        ]
        removed_folders = sum(entries[path].is_directory for path in descendants)
        removed_files = len(descendants) - removed_folders
        descendants.sort(key=lambda path: len(path.parts), reverse=True)
        for path in descendants:
            await client.remove(join_device_path(remote_root, path))
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
                    raise ValueError(f"Seuls les fichiers .bin sont acceptés : {source.name}")
                files.append((source, destination_for(source, [])))
                continue
            if not source.is_dir():
                raise FileNotFoundError(f"Source introuvable : {source}")
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
            raise ValueError("Aucun fichier .bin trouvé dans la sélection.")
        return files

    async def upload(
        self,
        sources: Iterable[Path],
        target_directory: str = "",
        *,
        progress_callback: TransferProgress | None = None,
    ) -> TransferReport:
        client, remote_root = self._require_client()
        target = _clean_relative(target_directory)
        files = self._collect_sources(sources, target)
        current_entries = await _walk_remote(client, remote_root)
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
                    f"Un fichier bloque la création du dossier {directory.as_posix()}."
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
                    f"Un dossier bloque le fichier {relative.as_posix()}."
                )
            if (
                existing is not None
                and existing.size == len(data)
                and await client.read_file(destination) == data
            ):
                report.identical += 1
                action = "identique"
            else:
                await _replace_file_safely(
                    client,
                    destination,
                    data,
                    destination_exists=existing is not None,
                )
                if existing is None:
                    report.created += 1
                    action = "ajouté"
                else:
                    report.overwritten += 1
                    action = "remplacé"
            current_entries[relative] = DirectoryEntry(relative.name, len(data), False)
            if progress_callback is not None:
                progress_callback(index, total, action, relative.as_posix())
        return report

    async def import_archive(
        self,
        archive_path: Path,
        *,
        progress_callback: TransferProgress | None = None,
    ) -> ImportReport:
        client, remote_root = self._require_client()
        with tempfile.TemporaryDirectory(prefix="Allmiibo-Import-") as temporary:
            output = Path(temporary) / "library"
            extraction = extract_archive(
                archive_path,
                output,
                conflict="overwrite",
            )
            synchronization = await self._sync_import(
                client,
                output,
                remote_root,
                progress_callback=progress_callback,
            )
        return ImportReport(extraction, synchronization)

    @staticmethod
    async def _sync_import(
        client: PixlVfsClient,
        output: Path,
        remote_root: str,
        *,
        progress_callback: TransferProgress | None,
    ) -> SyncReport:
        from allmiibo_ble import sync_directory

        return await sync_directory(
            client,
            output,
            remote_root,
            progress_callback=progress_callback,
        )
