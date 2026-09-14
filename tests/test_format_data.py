import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from format_data import (
    ArchiveError,
    ConflictError,
    extract_archive,
)


class FormatDataTests(unittest.TestCase):
    def make_archive(self, root: Path, files: dict[str, bytes]) -> Path:
        archive_path = root / "source.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return archive_path

    def test_preserves_drive_names_without_aliases_or_shortening(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/Animal Crossing x Sanrio Series/[AC] 001 - Isabelle.bin": b"ac",
                    "bundle/Super Smash Bros/SSB_90_-_Sephiroth.bin": b"ssb",
                    "bundle/Yu-Gi-Oh!/[YU-GI-OH] Yuga Oudou.bin": b"yugi",
                    "bundle/Monster Hunter Rise/MHR_Malzeno.bin": b"mhr",
                },
            )
            output = root / "data"

            extract_archive(archive, output)

            expected = {
                "Animal Crossing x Sanrio Series/[AC] 001 - Isabelle.bin",
                "Super Smash Bros/SSB_90_-_Sephiroth.bin",
                "Yu-Gi-Oh!/[YU-GI-OH] Yuga Oudou.bin",
                "Monster Hunter Rise/MHR_Malzeno.bin",
            }
            self.assertEqual(
                {path.relative_to(output).as_posix() for path in output.rglob("*.bin")},
                expected,
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
                (root / "data/Animal Crossing/[AC] 001 - Isabelle.bin").read_bytes(),
                b"amiibo",
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
            self.assertEqual(
                list(output.glob("*.bin")),
                [output / "[AC] 001 - Isabelle.bin"],
            )

    def test_default_conflict_policy_overwrites_different_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root, {"bundle/[AC] 001 - Isabelle.bin": b"new"}
            )
            output = root / "data"
            output.mkdir()
            target = output / "[AC] 001 - Isabelle.bin"
            target.write_bytes(b"old")

            report = extract_archive(archive, output)

            self.assertEqual(report.overwritten, 1)
            self.assertEqual(target.read_bytes(), b"new")

            second_report = extract_archive(archive, output)
            self.assertEqual(second_report.identical, 1)

    def test_default_policy_does_not_invent_a_name_for_archive_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "source.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("bundle/Exact name.bin", b"first")
                    archive.writestr("bundle/Exact name.bin", b"second")

            report = extract_archive(archive_path, root / "data")

            self.assertEqual((root / "data/Exact name.bin").read_bytes(), b"second")
            self.assertFalse((root / "data/Exact name (2).bin").exists())
            self.assertEqual(report.overwritten, 1)

    def test_dry_run_reports_files_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/[AC] 001 - Isabelle.bin": b"first",
                    "bundle/SSB_90_-_Sephiroth.bin": b"second",
                },
            )
            output = root / "data"

            report = extract_archive(archive, output, dry_run=True)

            self.assertEqual(report.extracted, 2)
            self.assertEqual(report.renamed, 0)
            self.assertFalse(output.exists())

    def test_long_names_are_kept_exactly_as_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/The Legend of Zelda/"
                    "The Legend of Zelda 30th Anniversary/"
                    "[ZLA] 01 - 8-bit Link (The Legend of Zelda).bin": b"link",
                },
            )
            output = root / "data"

            extract_archive(archive, output)

            expected = (
                output
                / "The Legend of Zelda"
                / "The Legend of Zelda 30th Anniversary"
                / "[ZLA] 01 - 8-bit Link (The Legend of Zelda).bin"
            )
            self.assertTrue(expected.is_file())

    def test_previous_short_name_is_not_migrated_or_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = b"sephiroth"
            archive = self.make_archive(
                root,
                {"bundle/Super Smash Bros/SSB_90_-_Sephiroth.bin": content},
            )
            output = root / "data"
            previous = output / "Super Smash Bros/Sephiroth.bin"
            previous.parent.mkdir(parents=True)
            previous.write_bytes(content)

            extract_archive(archive, output)

            self.assertTrue(previous.is_file())
            self.assertEqual(
                (output / "Super Smash Bros/SSB_90_-_Sephiroth.bin").read_bytes(),
                content,
            )

    def test_explicit_conflict_policies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root, {"bundle/[AC] 001 - Isabelle.bin": b"new"}
            )
            output = root / "data"
            output.mkdir()
            target = output / "[AC] 001 - Isabelle.bin"
            target.write_bytes(b"old")

            skipped = extract_archive(archive, output, conflict="skip")
            self.assertEqual(skipped.skipped, 1)
            self.assertEqual(target.read_bytes(), b"old")

            with self.assertRaises(ConflictError):
                extract_archive(archive, output, conflict="error")

            renamed = extract_archive(archive, output, conflict="rename")
            self.assertEqual(renamed.renamed, 1)
            self.assertEqual(
                (output / "[AC] 001 - Isabelle (2).bin").read_bytes(), b"new"
            )

    def test_rejects_zip_slip_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(root, {"../outside.bin": b"unsafe"})

            with self.assertRaises(ArchiveError):
                extract_archive(archive, root / "data")

            self.assertFalse((root / "outside.bin").exists())

    def test_reports_progress_for_each_archive_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = self.make_archive(
                root,
                {
                    "bundle/[AC] 001 - Isabelle.bin": b"one",
                    "bundle/SSB_90_-_Sephiroth.bin": b"two",
                },
            )
            events: list[tuple[int, int, str, Path]] = []

            extract_archive(
                archive,
                root / "data",
                progress_callback=lambda *event: events.append(event),
            )

            self.assertEqual([event[:2] for event in events], [(1, 2), (2, 2)])
            self.assertEqual(events[-1][3].name, "SSB_90_-_Sephiroth.bin")


if __name__ == "__main__":
    unittest.main()
