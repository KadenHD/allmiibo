"""Bluetooth LE client and one-way synchronizer for Pixl.js/Allmiibo devices."""

from __future__ import annotations

import asyncio
import os
import re
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol


NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

MAX_GATT_PACKET = 247
HEADER_SIZE = 4
MAX_WRITE_CHUNK = MAX_GATT_PACKET - HEADER_SIZE - 1
MAX_DEVICE_PATH_BYTES = 63
MAX_DEVICE_NAME_BYTES = 47

CMD_GET_VERSION = 0x01
CMD_GET_DRIVES = 0x10
CMD_OPEN_FILE = 0x12
CMD_CLOSE_FILE = 0x13
CMD_READ_FILE = 0x14
CMD_WRITE_FILE = 0x15
CMD_READ_DIR = 0x16
CMD_CREATE_DIR = 0x17
CMD_REMOVE = 0x18
CMD_RENAME = 0x19

MODE_READ = 8
MODE_WRITE = 22

DRIVE_PATH = re.compile(r"^[IE]:/")


class AllmiiboError(RuntimeError):
    """Base error for device communication and synchronization."""


class BluetoothDependencyError(AllmiiboError):
    """Raised when the optional Bleak dependency is unavailable."""


class DeviceNotFoundError(AllmiiboError):
    """Raised when no compatible BLE peripheral is discovered."""


class ProtocolError(AllmiiboError):
    """Raised for malformed or unexpected protocol data."""


class DeviceCommandError(AllmiiboError):
    """Raised when the device rejects a VFS command."""

    def __init__(self, command: int, message: str | None = None) -> None:
        detail = message or "commande refusée par l'appareil"
        super().__init__(f"Commande 0x{command:02x}: {detail}")
        self.command = command


@dataclass(frozen=True)
class Drive:
    status: int
    label: str
    name: str
    total_size: int
    free_size: int


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    size: int
    is_directory: bool


@dataclass
class SyncReport:
    created: int = 0
    overwritten: int = 0
    identical: int = 0
    folders_created: int = 0


class PacketTransport(Protocol):
    async def write(self, data: bytes) -> None: ...

    async def read(self, timeout: float) -> bytes: ...

    async def close(self) -> None: ...


class VfsClient(Protocol):
    async def get_drives(self) -> list[Drive]: ...

    async def read_directory(self, path: str) -> list[DirectoryEntry]: ...

    async def create_directory(self, path: str) -> None: ...

    async def read_file(self, path: str) -> bytes: ...

    async def write_file(self, path: str, data: bytes) -> None: ...

    async def remove(self, path: str) -> None: ...

    async def rename(self, source: str, destination: str) -> None: ...


def _pack_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFF:
        raise ValueError("Chaîne trop longue pour le protocole Pixl.js")
    return struct.pack("<H", len(encoded)) + encoded


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def take(self, length: int) -> bytes:
        if length < 0 or self.remaining < length:
            raise ProtocolError("Réponse BLE tronquée")
        result = self.data[self.offset : self.offset + length]
        self.offset += length
        return result

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def string(self) -> str:
        try:
            return self.take(self.u16()).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProtocolError("Texte UTF-8 invalide dans la réponse BLE") from error


def validate_device_path(path: str) -> None:
    if not DRIVE_PATH.match(path):
        raise ValueError(f"Chemin Allmiibo invalide: {path!r}")
    if "\\" in path or "//" in path[3:] or any(ord(char) < 32 for char in path):
        raise ValueError(f"Chemin Allmiibo invalide: {path!r}")

    relative = path[3:]
    parts = PurePosixPath(relative).parts if relative else ()
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Chemin Allmiibo invalide: {path!r}")
    if len(path.encode("utf-8")) > MAX_DEVICE_PATH_BYTES:
        raise ValueError(
            f"Chemin Allmiibo trop long ({len(path.encode('utf-8'))}/"
            f"{MAX_DEVICE_PATH_BYTES} octets): {path}"
        )
    for part in parts:
        if len(part.encode("utf-8")) > MAX_DEVICE_NAME_BYTES:
            raise ValueError(
                f"Nom Allmiibo trop long ({len(part.encode('utf-8'))}/"
                f"{MAX_DEVICE_NAME_BYTES} octets): {part}"
            )


def _compose_device_path(root: str, relative: PurePosixPath | str) -> str:
    suffix = str(relative).replace("\\", "/").strip("/")
    result = root.rstrip("/")
    if suffix:
        result = f"{result}/{suffix}"
    return result


def join_device_path(root: str, relative: PurePosixPath | str) -> str:
    result = _compose_device_path(root, relative)
    validate_device_path(result)
    return result


def _folder_keys(relative: PurePosixPath) -> list[PurePosixPath]:
    return [
        PurePosixPath(*relative.parts[:index])
        for index in range(1, len(relative.parts))
    ]


class BleakNusTransport:
    """Nordic UART transport backed by Bleak, imported only when used."""

    def __init__(self) -> None:
        self._client = None
        self._notifications: asyncio.Queue[bytes] = asyncio.Queue()

    async def connect(
        self, selector: str | None = None, scan_timeout: float = 15.0
    ) -> str:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as error:
            raise BluetoothDependencyError(
                "La dépendance Bluetooth manque. Exécuter: "
                "python -m pip install -r requirements.txt"
            ) from error

        wanted = selector.casefold() if selector else None

        def matches(device, advertisement) -> bool:
            services = {value.casefold() for value in advertisement.service_uuids}
            has_service = NUS_SERVICE_UUID in services
            if wanted is None:
                return has_service
            names = {
                value.casefold()
                for value in (device.name, advertisement.local_name, device.address)
                if value
            }
            return has_service and wanted in names

        device = await BleakScanner.find_device_by_filter(
            matches, timeout=scan_timeout
        )
        if device is None:
            suffix = f" correspondant à {selector!r}" if selector else ""
            raise DeviceNotFoundError(
                "Aucun appareil Pixl.js/Allmiibo détecté"
                f"{suffix}. Activer le mode Bluetooth Transmission."
            )

        client = BleakClient(device)
        await client.connect()
        self._client = client
        await client.start_notify(NUS_TX_UUID, self._on_notification)
        return device.name or device.address

    def _on_notification(self, _sender, data: bytearray) -> None:
        self._notifications.put_nowait(bytes(data))

    async def write(self, data: bytes) -> None:
        if self._client is None:
            raise AllmiiboError("Transport BLE non connecté")
        await self._client.write_gatt_char(NUS_RX_UUID, data, response=True)

    async def read(self, timeout: float) -> bytes:
        try:
            return await asyncio.wait_for(self._notifications.get(), timeout)
        except TimeoutError as error:
            raise ProtocolError(
                f"Aucune réponse de l'Allmiibo depuis {timeout:.1f} s"
            ) from error

    async def close(self) -> None:
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.stop_notify(NUS_TX_UUID)
                await self._client.disconnect()
        finally:
            self._client = None


class PixlVfsClient:
    def __init__(
        self,
        transport: PacketTransport,
        *,
        idle_timeout: float = 20.0,
        absolute_timeout: float = 180.0,
    ) -> None:
        self.transport = transport
        self.idle_timeout = idle_timeout
        self.absolute_timeout = absolute_timeout
        self._lock = asyncio.Lock()

    async def _request(self, command: int, payload: bytes = b"") -> bytes:
        packet = struct.pack("<BBH", command, 0, 0) + payload
        if len(packet) > MAX_GATT_PACKET:
            raise ValueError(
                f"Requête 0x{command:02x} trop longue: {len(packet)} octets"
            )

        async with self._lock:
            await self.transport.write(packet)
            loop = asyncio.get_running_loop()
            absolute_deadline = loop.time() + self.absolute_timeout
            response = bytearray()
            first = True

            while True:
                remaining = absolute_deadline - loop.time()
                if remaining <= 0:
                    raise ProtocolError(
                        f"Délai absolu dépassé pour la commande 0x{command:02x}"
                    )
                frame = await self.transport.read(min(self.idle_timeout, remaining))
                if len(frame) < HEADER_SIZE:
                    raise ProtocolError("Trame BLE plus courte que son en-tête")

                response_command, status, chunk = struct.unpack("<BBH", frame[:4])
                if response_command != command:
                    raise ProtocolError(
                        f"Réponse 0x{response_command:02x} reçue pour la commande "
                        f"0x{command:02x}"
                    )
                if status != 0:
                    raise DeviceCommandError(command)

                response.extend(frame if first else frame[HEADER_SIZE:])
                first = False
                if chunk & 0x8000 == 0:
                    return bytes(response[HEADER_SIZE:])

    async def get_version(self) -> str:
        return _Reader(await self._request(CMD_GET_VERSION)).string()

    async def get_drives(self) -> list[Drive]:
        reader = _Reader(await self._request(CMD_GET_DRIVES))
        drives = []
        for _ in range(reader.u8()):
            drives.append(
                Drive(
                    status=reader.u8(),
                    label=chr(reader.u8()),
                    name=reader.string(),
                    total_size=reader.u32(),
                    free_size=reader.u32(),
                )
            )
        if reader.remaining:
            raise ProtocolError("Données superflues dans la liste des disques")
        return drives

    async def _open_file(self, path: str, mode: int) -> int:
        validate_device_path(path)
        response = await self._request(
            CMD_OPEN_FILE, _pack_string(path) + struct.pack("<I", mode)
        )
        if len(response) != 1:
            raise ProtocolError("Identifiant de fichier absent ou invalide")
        return response[0]

    async def _close_file(self, file_id: int) -> None:
        await self._request(CMD_CLOSE_FILE, bytes((file_id,)))

    async def read_file(self, path: str) -> bytes:
        file_id = await self._open_file(path, MODE_READ)
        try:
            return await self._request(CMD_READ_FILE, bytes((file_id,)))
        finally:
            await self._close_file(file_id)

    async def write_file(self, path: str, data: bytes) -> None:
        file_id = await self._open_file(path, MODE_WRITE)
        try:
            for offset in range(0, len(data), MAX_WRITE_CHUNK):
                chunk = data[offset : offset + MAX_WRITE_CHUNK]
                await self._request(CMD_WRITE_FILE, bytes((file_id,)) + chunk)
        finally:
            await self._close_file(file_id)

    async def read_directory(self, path: str) -> list[DirectoryEntry]:
        validate_device_path(path)
        reader = _Reader(await self._request(CMD_READ_DIR, _pack_string(path)))
        entries = []
        while reader.remaining:
            name = reader.string()
            size = reader.u32()
            entry_type = reader.u8()
            metadata_length = reader.u8()
            if metadata_length != 0xFF:
                reader.take(metadata_length)
            entries.append(
                DirectoryEntry(
                    name=name,
                    size=size,
                    is_directory=entry_type != 0,
                )
            )
        return entries

    async def create_directory(self, path: str) -> None:
        validate_device_path(path)
        await self._request(CMD_CREATE_DIR, _pack_string(path))

    async def remove(self, path: str) -> None:
        validate_device_path(path)
        await self._request(CMD_REMOVE, _pack_string(path))

    async def rename(self, source: str, destination: str) -> None:
        validate_device_path(source)
        validate_device_path(destination)
        await self._request(
            CMD_RENAME, _pack_string(source) + _pack_string(destination)
        )


def _collect_local_tree(local_root: Path) -> tuple[list[PurePosixPath], list[Path]]:
    if not local_root.is_dir():
        raise FileNotFoundError(f"Dossier local introuvable: {local_root}")

    files: list[Path] = []
    for current, dirnames, filenames in os.walk(local_root):
        dirnames.sort(key=str.casefold)
        for filename in sorted(filenames, key=str.casefold):
            if filename.lower().endswith(".bin"):
                path = Path(current) / filename
                if path.is_symlink():
                    raise ValueError(f"Lien symbolique local non pris en charge: {path}")
                files.append(path)

    directories_set: set[PurePosixPath] = set()
    for path in files:
        relative = PurePosixPath(*path.relative_to(local_root).parts)
        directories_set.update(_folder_keys(relative))
    directories = list(directories_set)
    directories.sort(key=lambda item: (len(item.parts), str(item).casefold()))
    files.sort(key=lambda item: str(item.relative_to(local_root)).casefold())
    return directories, files


async def _walk_remote(
    client: VfsClient, root: str
) -> dict[PurePosixPath, DirectoryEntry]:
    result: dict[PurePosixPath, DirectoryEntry] = {}

    async def visit(path: str, relative: PurePosixPath) -> None:
        for entry in await client.read_directory(path):
            child_relative = relative / entry.name
            child_path = join_device_path(root, child_relative)
            result[child_relative] = entry
            if entry.is_directory:
                await visit(child_path, child_relative)

    await visit(root, PurePosixPath())
    return result


async def _ensure_remote_root(
    client: VfsClient, root: str, *, dry_run: bool
) -> tuple[bool, int]:
    drive_root = root[:3]
    components = PurePosixPath(root[3:]).parts
    current = drive_root
    created = 0

    for index, component in enumerate(components):
        entries = await client.read_directory(current)
        match = next((entry for entry in entries if entry.name == component), None)
        current = join_device_path(current, component)
        if match is None:
            if dry_run:
                return False, created + len(components) - index
            await client.create_directory(current)
            created += 1
        elif not match.is_directory:
            raise AllmiiboError(
                f"Un fichier empêche la création du dossier distant: {current}"
            )
    return True, created


async def _replace_file_safely(
    client: VfsClient, path: str, data: bytes, *, destination_exists: bool
) -> None:
    drive_root = path[:3]
    token = uuid.uuid4().hex[:8]
    temporary = f"{drive_root}.allmiibo-{token}.tmp"
    backup = f"{drive_root}.allmiibo-{token}.bak"

    try:
        await client.write_file(temporary, data)
        if await client.read_file(temporary) != data:
            raise ProtocolError(f"Vérification après transfert échouée: {path}")

        if not destination_exists:
            await client.rename(temporary, path)
            return

        await client.rename(path, backup)
        try:
            await client.rename(temporary, path)
        except Exception as replacement_error:
            try:
                await client.rename(backup, path)
            except Exception as rollback_error:
                raise AllmiiboError(
                    "Remplacement et restauration impossibles. Les données restent "
                    f"récupérables dans {temporary} et {backup}."
                ) from rollback_error
            raise AllmiiboError(
                f"Remplacement annulé et ancien fichier restauré: {path}"
            ) from replacement_error
        await client.remove(backup)
    except Exception:
        try:
            await client.remove(temporary)
        except Exception:
            pass
        raise


async def sync_directory(
    client: VfsClient,
    local_root: Path,
    remote_root: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    show_progress: bool = False,
) -> SyncReport:
    """Push local .bin files, overwrite differences, and keep remote-only files."""
    validate_device_path(remote_root)
    if remote_root in {"E:/", "I:/"}:
        raise ValueError("La synchronisation doit cibler un sous-dossier du disque")

    directories, files = _collect_local_tree(local_root)
    local_file_items = [
        (
            PurePosixPath(*path.relative_to(local_root).parts),
            path,
            path.stat().st_size,
        )
        for path in files
    ]

    for relative in directories:
        join_device_path(remote_root, relative)
    for relative, _path, _size in local_file_items:
        join_device_path(remote_root, relative)

    root_exists, root_folders_created = await _ensure_remote_root(
        client, remote_root, dry_run=dry_run
    )
    remote = await _walk_remote(client, remote_root) if root_exists else {}
    report = SyncReport(folders_created=root_folders_created)

    for relative in directories:
        entry = remote.get(relative)
        destination = join_device_path(remote_root, relative)
        if entry is not None and not entry.is_directory:
            raise AllmiiboError(
                f"Un fichier distant bloque le dossier local: {destination}"
            )
        if entry is None:
            report.folders_created += 1
            if verbose:
                print(f"dossier    {destination}")
            if not dry_run:
                await client.create_directory(destination)

    total = len(local_file_items)
    for position, (relative, local_path, local_size) in enumerate(
        local_file_items, start=1
    ):
        destination = join_device_path(remote_root, relative)
        entry = remote.get(relative)
        if entry is not None and entry.is_directory:
            raise AllmiiboError(
                f"Un dossier distant bloque le fichier local: {destination}"
            )

        local_data = local_path.read_bytes()
        destination_exists = entry is not None
        if entry is not None and entry.size == local_size:
            if await client.read_file(destination) == local_data:
                report.identical += 1
                if verbose:
                    print(f"identique  {destination}")
                elif show_progress:
                    _show_progress(position, total, "identique")
                continue

        if destination_exists:
            report.overwritten += 1
            action = "remplacé"
        else:
            report.created += 1
            action = "envoyé"
        if verbose:
            print(f"{action:10} {destination}")
        if not dry_run:
            await _replace_file_safely(
                client,
                destination,
                local_data,
                destination_exists=destination_exists,
            )
        if show_progress:
            _show_progress(position, total, action)

    return report


def _show_progress(current: int, total: int, action: str) -> None:
    width = 28
    completed = width if total == 0 else round(width * current / total)
    bar = "█" * completed + "░" * (width - completed)
    print(f"\r[{bar}] {current}/{total} {action:<10}", end="", flush=True)
    if current == total:
        print()


def choose_remote_root(
    drives: list[Drive], requested_drive: str | None, folder: str
) -> str:
    available = {drive.label: drive for drive in drives if drive.status == 0}
    if requested_drive is not None:
        label = requested_drive.upper()
        if label not in available:
            raise AllmiiboError(f"Disque {label}: indisponible sur l'Allmiibo")
    else:
        label = next(
            (candidate for candidate in ("E", "I") if candidate in available),
            "",
        )
        if not label:
            raise AllmiiboError("Aucun disque disponible sur l'Allmiibo")

    clean_folder = folder.replace("\\", "/").strip("/")
    if not clean_folder or ":" in clean_folder:
        raise ValueError("--device-root doit être un sous-dossier relatif, ex. amiibo")
    return join_device_path(f"{label}:/", clean_folder)


async def sync_to_device(
    local_root: Path,
    *,
    selector: str | None = None,
    drive: str | None = None,
    device_root: str = "amiibo",
    scan_timeout: float = 15.0,
    response_timeout: float = 20.0,
    dry_run: bool = False,
    verbose: bool = False,
    show_progress: bool = False,
) -> tuple[str, str, SyncReport]:
    transport = BleakNusTransport()
    try:
        device_name = await transport.connect(selector, scan_timeout)
        if show_progress:
            print(f"Connecté à {device_name}. Inventaire des fichiers distants…")
        client = PixlVfsClient(transport, idle_timeout=response_timeout)
        drives = await client.get_drives()
        remote_root = choose_remote_root(drives, drive, device_root)
        report = await sync_directory(
            client,
            local_root,
            remote_root,
            dry_run=dry_run,
            verbose=verbose,
            show_progress=show_progress,
        )
        return device_name, remote_root, report
    finally:
        await transport.close()
