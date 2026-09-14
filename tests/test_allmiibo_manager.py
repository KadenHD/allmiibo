import tempfile
import unittest
import zipfile
from pathlib import Path

from allmiibo_manager import AllmiiboManager, ConnectionInfo
from tests.test_allmiibo_ble import FakeVfs


def connected_manager(client: FakeVfs) -> AllmiiboManager:
    manager = AllmiiboManager()
    manager.client = client  # type: ignore[assignment]
    manager.remote_root = "E:/amiibo"
    return manager


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_refreshes_the_visible_storage_information(self) -> None:
        client = FakeVfs()
        manager = connected_manager(client)
        manager.info = ConnectionInfo("Allmiibo", "2.1.0", 1, 0)

        info = await manager.refresh_info()

        self.assertEqual(info.device_name, "Allmiibo")
        self.assertEqual(info.firmware_version, "2.1.0")
        self.assertEqual(info.total_size, 2_000_000)
        self.assertEqual(info.free_size, 1_000_000)

    async def test_lists_the_remote_library_without_exposing_the_drive(self) -> None:
        client = FakeVfs()
        client.directories.add("E:/amiibo/Zelda")
        client.files["E:/amiibo/Zelda/Link.bin"] = b"link"

        items = await connected_manager(client).list_library()

        self.assertEqual(
            [(item.relative_path, item.is_directory) for item in items],
            [("Zelda", True), ("Zelda/Link.bin", False)],
        )

    async def test_library_cache_avoids_repeated_ble_walks(self) -> None:
        client = FakeVfs()
        client.directories.add("E:/amiibo/Zelda")
        client.files["E:/amiibo/Zelda/Link.bin"] = b"link"
        manager = connected_manager(client)

        await manager.list_library()
        initial_reads = client.read_directory_count
        await manager.list_library()

        self.assertEqual(client.read_directory_count, initial_reads)

        client.files["E:/amiibo/Zelda/Zelda.bin"] = b"zelda"
        cached = await manager.list_library()
        self.assertNotIn("Zelda/Zelda.bin", {item.relative_path for item in cached})

        refreshed = await manager.list_library(force_refresh=True)
        self.assertGreater(client.read_directory_count, initial_reads)
        self.assertIn("Zelda/Zelda.bin", {item.relative_path for item in refreshed})

    async def test_mutations_update_cache_without_another_ble_walk(self) -> None:
        client = FakeVfs()
        client.directories.add("E:/amiibo/Zelda")
        client.files["E:/amiibo/Zelda/Link.bin"] = b"link"
        manager = connected_manager(client)
        await manager.list_library()
        initial_reads = client.read_directory_count

        await manager.create_folder("", "Smash")
        await manager.rename("Zelda/Link.bin", "Hero.bin")
        await manager.delete("Zelda/Hero.bin")
        items = await manager.list_library()

        self.assertEqual(client.read_directory_count, initial_reads)
        self.assertIn("Smash", {item.relative_path for item in items})
        self.assertNotIn("Zelda/Hero.bin", {item.relative_path for item in items})

    async def test_full_refresh_reports_each_scanned_stage(self) -> None:
        client = FakeVfs()
        client.directories.add("E:/amiibo/Zelda")
        client.files["E:/amiibo/Zelda/Link.bin"] = b"link"
        messages: list[str] = []

        await connected_manager(client).list_library(
            force_refresh=True,
            status_callback=messages.append,
        )

        self.assertTrue(any("Reading folder: Library" in value for value in messages))
        self.assertTrue(any("Folder scanned: Zelda" in value for value in messages))
        self.assertTrue(any("Index complete" in value for value in messages))

    async def test_manual_upload_merges_without_rewriting_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            same = root / "[AC] 001 - Isabelle.bin"
            changed = root / "SSB_90_-_Sephiroth.bin"
            new = root / "[YU-GI-OH] Yuga Oudou.bin"
            same.write_bytes(b"same")
            changed.write_bytes(b"new")
            new.write_bytes(b"yugi")
            client = FakeVfs()
            client.files["E:/amiibo/[AC] 001 - Isabelle.bin"] = b"same"
            client.files["E:/amiibo/SSB_90_-_Sephiroth.bin"] = b"old"
            events: list[tuple[int, int, str, str]] = []

            report = await connected_manager(client).upload(
                [same, changed, new],
                progress_callback=lambda *event: events.append(event),
            )

            self.assertEqual(report.identical, 1)
            self.assertEqual(report.overwritten, 1)
            self.assertEqual(report.created, 1)
            self.assertEqual(
                client.files["E:/amiibo/SSB_90_-_Sephiroth.bin"], b"new"
            )
            self.assertEqual(
                client.files["E:/amiibo/[YU-GI-OH] Yuga Oudou.bin"], b"yugi"
            )
            self.assertEqual(len(events), 3)

    async def test_distinct_source_names_remain_distinct_on_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "[AC] 001 - Isabelle.bin"
            second_dir = root / "second"
            second_dir.mkdir()
            second = second_dir / "Isabelle.bin"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            client = FakeVfs()

            report = await connected_manager(client).upload([first, second])

            self.assertEqual(report.created, 2)
            self.assertEqual(report.identical, 0)
            self.assertEqual(client.write_count, 2)
            self.assertIn("E:/amiibo/[AC] 001 - Isabelle.bin", client.files)
            self.assertIn("E:/amiibo/Isabelle.bin", client.files)

    async def test_deletes_a_folder_from_the_bottom_up(self) -> None:
        client = FakeVfs()
        client.directories.update(
            {"E:/amiibo/Zelda", "E:/amiibo/Zelda/BOTW"}
        )
        client.files.update(
            {
                "E:/amiibo/Zelda/Link.bin": b"link",
                "E:/amiibo/Zelda/BOTW/Mipha.bin": b"mipha",
            }
        )

        removed = await connected_manager(client).delete("Zelda")

        self.assertEqual(removed.total, 4)
        self.assertEqual(removed.removed_files, 2)
        self.assertEqual(removed.removed_folders, 2)
        self.assertFalse(any(path.startswith("E:/amiibo/Zelda") for path in client.files))
        self.assertNotIn("E:/amiibo/Zelda", client.directories)

    async def test_deletes_multiple_checked_folders_in_one_operation(self) -> None:
        client = FakeVfs()
        client.directories.update({"E:/amiibo/Zelda", "E:/amiibo/Smash"})
        client.files.update(
            {
                "E:/amiibo/Zelda/Link.bin": b"link",
                "E:/amiibo/Smash/Mario.bin": b"mario",
            }
        )

        removed = await connected_manager(client).delete_many(["Zelda", "Smash"])

        self.assertEqual(removed.total, 4)
        self.assertEqual(removed.requested, ("Smash", "Zelda"))
        self.assertNotIn("E:/amiibo/Zelda", client.directories)
        self.assertNotIn("E:/amiibo/Smash", client.directories)
        self.assertEqual(client.files, {})

    async def test_never_deletes_fav_data_or_a_parent_containing_them(self) -> None:
        client = FakeVfs()
        client.directories.update(
            {
                "E:/amiibo/fav",
                "E:/amiibo/DATA",
                "E:/amiibo/Collection",
                "E:/amiibo/Collection/data",
            }
        )
        manager = connected_manager(client)

        for target in ("fav", "DATA", "Collection"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "must always be preserved"):
                    await manager.delete(target)

        self.assertIn("E:/amiibo/fav", client.directories)
        self.assertIn("E:/amiibo/DATA", client.directories)
        self.assertIn("E:/amiibo/Collection/data", client.directories)

    async def test_never_renames_protected_folders(self) -> None:
        client = FakeVfs()
        client.directories.add("E:/amiibo/fav")

        with self.assertRaisesRegex(ValueError, "cannot be renamed"):
            await connected_manager(client).rename("fav", "Favoris")

        self.assertIn("E:/amiibo/fav", client.directories)

    async def test_manual_names_keep_underscores_and_prefixes(self) -> None:
        client = FakeVfs()
        client.files["E:/amiibo/SSB_90_-_Sephiroth.bin"] = b"ssb"
        manager = connected_manager(client)

        folder = await manager.create_folder("", "My_Custom_Folder")
        renamed = await manager.rename(
            "SSB_90_-_Sephiroth.bin", "[SSB] 090 - Sephiroth"
        )

        self.assertEqual(folder, "My_Custom_Folder")
        self.assertIn("E:/amiibo/My_Custom_Folder", client.directories)
        self.assertEqual(renamed, "[SSB] 090 - Sephiroth.bin")
        self.assertIn("E:/amiibo/[SSB] 090 - Sephiroth.bin", client.files)

    async def test_rejects_a_duplicate_folder_name_in_the_same_directory(self) -> None:
        client = FakeVfs()
        client.directories.update(
            {"E:/amiibo/Zelda", "E:/amiibo/Other"}
        )
        manager = connected_manager(client)

        with self.assertRaisesRegex(FileExistsError, "already exists"):
            await manager.create_folder("", "zelda")

        nested = await manager.create_folder("Other", "Zelda")
        self.assertEqual(nested, "Other/Zelda")
        self.assertIn("E:/amiibo/Other/Zelda", client.directories)

    async def test_bin_rename_always_keeps_the_bin_extension(self) -> None:
        client = FakeVfs()
        client.files["E:/amiibo/Link.bin"] = b"link"
        manager = connected_manager(client)

        renamed = await manager.rename("Link.bin", "Hero.txt")

        self.assertEqual(renamed, "Hero.txt.bin")
        self.assertIn("E:/amiibo/Hero.txt.bin", client.files)

    async def test_rename_rejects_a_sibling_name_collision(self) -> None:
        client = FakeVfs()
        client.files.update(
            {
                "E:/amiibo/Link.bin": b"link",
                "E:/amiibo/Zelda.bin": b"zelda",
            }
        )

        with self.assertRaisesRegex(FileExistsError, "already exists"):
            await connected_manager(client).rename("Link.bin", "zelda.bin")

        self.assertIn("E:/amiibo/Link.bin", client.files)

    async def test_zip_import_updates_without_removing_remote_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "amiibo.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("bundle/[AC] 001 - Isabelle.bin", b"new")
                archive.writestr("bundle/SSB_90_-_Sephiroth.bin", b"same")

            client = FakeVfs()
            client.files.update(
                {
                    "E:/amiibo/[AC] 001 - Isabelle.bin": b"old",
                    "E:/amiibo/SSB_90_-_Sephiroth.bin": b"same",
                    "E:/amiibo/Personal.bin": b"keep",
                }
            )

            manager = connected_manager(client)
            await manager.list_library()
            initial_reads = client.read_directory_count
            report = await manager.import_archive(archive_path)

            self.assertEqual(report.synchronization.overwritten, 1)
            self.assertEqual(report.synchronization.identical, 1)
            self.assertEqual(
                client.files["E:/amiibo/[AC] 001 - Isabelle.bin"], b"new"
            )
            self.assertEqual(client.files["E:/amiibo/Personal.bin"], b"keep")
            self.assertEqual(client.read_directory_count, initial_reads)


if __name__ == "__main__":
    unittest.main()
