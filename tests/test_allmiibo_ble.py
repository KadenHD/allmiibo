import asyncio
import struct
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from allmiibo_ble import (
    CMD_CLOSE_FILE,
    CMD_OPEN_FILE,
    CMD_READ_FILE,
    CMD_WRITE_FILE,
    MAX_WRITE_CHUNK,
    DirectoryEntry,
    Drive,
    PixlVfsClient,
    join_device_path,
    sync_directory,
    validate_device_path,
)


def response(command: int, payload: bytes = b"", chunk: int = 0) -> bytes:
    return struct.pack("<BBH", command, 0, chunk) + payload


class ScriptedTransport:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.pending: asyncio.Queue[bytes] = asyncio.Queue()

    async def write(self, data: bytes) -> None:
        self.writes.append(data)
        command = data[0]
        if command == CMD_OPEN_FILE:
            await self.pending.put(response(command, b"\x07"))
        elif command == CMD_READ_FILE:
            await self.pending.put(response(command, b"first", 0x8000))
            await self.pending.put(response(command, b"second", 1))
        else:
            await self.pending.put(response(command))

    async def read(self, timeout: float) -> bytes:
        return await asyncio.wait_for(self.pending.get(), timeout)

    async def close(self) -> None:
        pass


class FakeVfs:
    def __init__(self) -> None:
        self.directories = {"E:/", "E:/amiibo"}
        self.files: dict[str, bytes] = {}
        self.write_count = 0

    async def get_drives(self) -> list[Drive]:
        return [Drive(0, "E", "External Flash", 2_000_000, 1_000_000)]

    async def read_directory(self, path: str) -> list[DirectoryEntry]:
        prefix = path.rstrip("/") + "/"
        entries: dict[str, DirectoryEntry] = {}
        for directory in self.directories:
            if directory in {path, "E:/"}:
                continue
            if directory.startswith(prefix):
                remainder = directory[len(prefix) :].strip("/")
                if remainder and "/" not in remainder:
                    entries[remainder] = DirectoryEntry(remainder, 0, True)
        for file_path, content in self.files.items():
            if file_path.startswith(prefix):
                remainder = file_path[len(prefix) :]
                if remainder and "/" not in remainder:
                    entries[remainder] = DirectoryEntry(
                        remainder, len(content), False
                    )
        return list(entries.values())

    async def create_directory(self, path: str) -> None:
        self.directories.add(path)

    async def read_file(self, path: str) -> bytes:
        return self.files[path]

    async def write_file(self, path: str, data: bytes) -> None:
        self.write_count += 1
        self.files[path] = bytes(data)

    async def remove(self, path: str) -> None:
        if path in self.files:
            del self.files[path]
        else:
            self.directories.remove(path)

    async def rename(self, source: str, destination: str) -> None:
        self.files[destination] = self.files.pop(source)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_reassembles_notifications(self) -> None:
        transport = ScriptedTransport()
        client = PixlVfsClient(transport)

        content = await client.read_file("E:/amiibo/test.bin")

        self.assertEqual(content, b"firstsecond")
        self.assertEqual([packet[0] for packet in transport.writes], [18, 20, 19])

    async def test_write_uses_u32_mode_and_242_byte_chunks(self) -> None:
        transport = ScriptedTransport()
        client = PixlVfsClient(transport)
        content = bytes(range(250)) * 2

        await client.write_file("E:/amiibo/test.bin", content)

        open_packet = transport.writes[0]
        path_length = struct.unpack("<H", open_packet[4:6])[0]
        mode_offset = 6 + path_length
        self.assertEqual(struct.unpack("<I", open_packet[mode_offset:])[0], 22)

        writes = [packet for packet in transport.writes if packet[0] == CMD_WRITE_FILE]
        self.assertEqual(len(writes), 3)
        self.assertTrue(all(len(packet) <= 247 for packet in writes))
        self.assertEqual(len(writes[0]) - 5, MAX_WRITE_CHUNK)
        self.assertEqual(transport.writes[-1][0], CMD_CLOSE_FILE)


class SyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_ignores_same_overwrites_different_and_keeps_extra(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            (local / "nested").mkdir()
            (local / "same.bin").write_bytes(b"same")
            (local / "different.bin").write_bytes(b"new!")
            (local / "new.bin").write_bytes(b"created")
            (local / "nested/child.bin").write_bytes(b"child")
            (local / "ignored.txt").write_text("not transferred", encoding="utf-8")

            client = FakeVfs()
            client.files.update(
                {
                    "E:/amiibo/same.bin": b"same",
                    "E:/amiibo/different.bin": b"old!",
                    "E:/amiibo/extra.bin": b"keep",
                }
            )

            report = await sync_directory(client, local, "E:/amiibo")

            self.assertEqual(report.identical, 1)
            self.assertEqual(report.overwritten, 1)
            self.assertEqual(report.created, 2)
            self.assertEqual(report.folders_created, 1)
            self.assertEqual(client.files["E:/amiibo/different.bin"], b"new!")
            self.assertEqual(client.files["E:/amiibo/new.bin"], b"created")
            self.assertEqual(client.files["E:/amiibo/nested/child.bin"], b"child")
            self.assertEqual(client.files["E:/amiibo/extra.bin"], b"keep")
            self.assertNotIn("E:/amiibo/ignored.txt", client.files)

    async def test_sync_rejects_non_formatted_long_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            directory = local / "A very long collection name" / "Another long series name"
            directory.mkdir(parents=True)
            source = directory / "A character with a very long display name.bin"
            source.write_bytes(b"amiibo")

            with self.assertRaises(ValueError):
                await sync_directory(FakeVfs(), local, "E:/amiibo")

    async def test_dry_run_does_not_mutate_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary)
            (local / "different.bin").write_bytes(b"new")
            client = FakeVfs()
            client.files["E:/amiibo/different.bin"] = b"old"

            report = await sync_directory(
                client, local, "E:/amiibo", dry_run=True
            )

            self.assertEqual(report.overwritten, 1)
            self.assertEqual(client.files["E:/amiibo/different.bin"], b"old")
            self.assertEqual(client.write_count, 0)


class PathTests(unittest.TestCase):
    def test_device_paths_are_joined_and_validated(self) -> None:
        self.assertEqual(
            join_device_path("E:/amiibo", PurePosixPath("Zelda/Link.bin")),
            "E:/amiibo/Zelda/Link.bin",
        )
        validate_device_path("E:/amiibo/Épona.bin")

        with self.assertRaises(ValueError):
            validate_device_path("E:/amiibo/../settings.bin")
        with self.assertRaises(ValueError):
            validate_device_path("E:/amiibo/" + "x" * 60 + ".bin")


if __name__ == "__main__":
    unittest.main()
