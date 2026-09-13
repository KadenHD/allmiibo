import tempfile
import unittest
import zipfile
from pathlib import Path

from format_data import (
    ArchiveError,
    ConflictError,
    extract_archive,
    normalize_bin_name,
)


class FormatDataTests(unittest.TestCase):
    def make_archive(self, root: Path, files: dict[str, bytes]) -> Path:
        archive_path = root / "source.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return archive_path

    def test_normalizes_only_matching_bin_names(self) -> None:
        self.assertEqual(normalize_bin_name("[AC] 001 - Isabelle.bin"), "Isabelle.bin")
        self.assertEqual(
            normalize_bin_name("SSB_90_-_Sephiroth.bin"), "Sephiroth.bin"
        )
        self.assertEqual(
            normalize_bin_name("[YU-GI-OH] Yuga Oudou.bin"),
            "Yuga Oudou.bin",
        )
        self.assertEqual(normalize_bin_name("MHR_Malzeno.bin"), "Malzeno.bin")
        self.assertEqual(
            normalize_bin_name("08-Solaire of Astora.bin"), "Solaire of Astora.bin"
        )
        self.assertEqual(
            normalize_bin_name("[AC] 001 - notes.txt"), "[AC] 001 - notes.txt"
        )

    def test_extracts_hierarchy_without_common_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/Animal Crossing/[AC] 001 - Isabelle.bin": b"amiibo",
                    "bundle/readme.txt": b"notes",
                },
            )

            report = extract_archive(archive, root / "data")

            self.assertEqual(report.extracted, 2)
            self.assertEqual(
                (root / "data/Animal Crossing/Isabelle.bin").read_bytes(), b"amiibo"
            )
            self.assertEqual((root / "data/readme.txt").read_bytes(), b"notes")

    def test_identical_file_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root, {"bundle/[AC] 001 - Isabelle.bin": b"same"}
            )
            output = root / "data"

            extract_archive(archive, output)
            report = extract_archive(archive, output)

            self.assertEqual(report.extracted, 0)
            self.assertEqual(report.identical, 1)
            self.assertEqual(list(output.glob("*.bin")), [output / "Isabelle.bin"])

    def test_default_conflict_policy_overwrites_different_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root, {"bundle/[AC] 001 - Isabelle.bin": b"new"}
            )
            output = root / "data"
            output.mkdir()
            (output / "Isabelle.bin").write_bytes(b"old")

            report = extract_archive(archive, output)

            self.assertEqual(report.overwritten, 1)
            self.assertEqual((output / "Isabelle.bin").read_bytes(), b"new")

            second_report = extract_archive(archive, output)
            self.assertEqual(second_report.identical, 1)

    def test_dry_run_resolves_collisions_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/[AC] 001 - Isabelle.bin": b"first",
                    "bundle/[AC] 101 - Isabelle.bin": b"second",
                },
            )
            output = root / "data"

            report = extract_archive(archive, output, dry_run=True)

            self.assertEqual(report.extracted, 2)
            self.assertEqual(report.renamed, 1)
            self.assertFalse(output.exists())

    def test_final_data_path_is_readable_and_device_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/The Legend of Zelda/"
                    "The Legend of Zelda 30th Anniversary/"
                    "[ZLA] 01 - 8-bit Link (The Legend of Zelda).bin": b"link",
                    "bundle/Super Smash Bros/SSB_90_-_Sephiroth.bin": b"ssb",
                    "bundle/Yu-Gi-Oh!/[YU-GI-OH] Yuga Oudou.bin": b"yugi",
                },
            )
            output = root / "data"

            report = extract_archive(archive, output)

            expected = [
                output / "Zelda/30th Anniversary/8-bit Link (Zelda).bin",
                output / "Super Smash Bros/Sephiroth.bin",
                output / "Yu-Gi-Oh!/Yuga Oudou.bin",
            ]
            self.assertTrue(all(path.is_file() for path in expected))
            self.assertEqual(report.normalized, 3)
            self.assertGreaterEqual(report.shortened, 1)
            for path in expected:
                device_path = "E:/amiibo/" + path.relative_to(output).as_posix()
                self.assertLessEqual(len(device_path.encode("utf-8")), 63)
                self.assertLessEqual(len(path.name.encode("utf-8")), 47)

    def test_previous_generated_paths_are_migrated_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b"sephiroth"
            archive = self.make_archive(
                root,
                {"bundle/Super Smash Bros/SSB_90_-_Sephiroth.bin": content},
            )
            output = root / "data"
            legacy = output / "Super Smash Bros/SSB_90_-_Sephiroth.bin"
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(content)

            report = extract_archive(archive, output)

            self.assertFalse(legacy.exists())
            self.assertEqual(
                (output / "Super Smash Bros/Sephiroth.bin").read_bytes(), content
            )
            self.assertEqual(report.legacy_removed, 1)

    def test_explicit_conflict_policies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root, {"bundle/[AC] 001 - Isabelle.bin": b"new"}
            )
            output = root / "data"
            output.mkdir()
            target = output / "Isabelle.bin"
            target.write_bytes(b"old")

            skipped = extract_archive(archive, output, conflict="skip")
            self.assertEqual(skipped.skipped, 1)
            self.assertEqual(target.read_bytes(), b"old")

            with self.assertRaises(ConflictError):
                extract_archive(archive, output, conflict="error")

            renamed = extract_archive(archive, output, conflict="rename")
            self.assertEqual(renamed.renamed, 1)
            self.assertEqual((output / "Isabelle (2).bin").read_bytes(), b"new")

    def test_rejects_zip_slip_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(root, {"../outside.bin": b"unsafe"})

            with self.assertRaises(ArchiveError):
                extract_archive(archive, root / "data")

            self.assertFalse((root / "outside.bin").exists())


if __name__ == "__main__":
    unittest.main()
