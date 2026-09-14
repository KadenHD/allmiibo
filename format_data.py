#!/usr/bin/env python3
"""Extract an Allmiibo ZIP archive into data/ without rewriting its names."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Iterable, Literal


ConflictPolicy = Literal["error", "skip", "overwrite", "rename"]
ExtractionProgress = Callable[[int, int, str, Path], None]


class ArchiveError(ValueError):
    """Raised when an archive contains an unsafe or unsupported entry."""


class ConflictError(FileExistsError):
    """Raised when a destination conflict cannot be resolved."""


@dataclass
class ExtractionReport:
    extracted: int = 0
    renamed: int = 0
    overwritten: int = 0
    identical: int = 0
    skipped: int = 0


def _safe_parts(member_name: str) -> tuple[str, ...]:
    if "\\" in member_name:
        raise ArchiveError(f"Unsafe ZIP path (backslash): {member_name!r}")

    path = PurePosixPath(member_name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveError(f"Unsafe ZIP path: {member_name!r}")

    return path.parts


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _common_root(entries: Iterable[zipfile.ZipInfo]) -> str | None:
    roots: set[str] = set()
    saw_nested_entry = False

    for info in entries:
        parts = _safe_parts(info.filename)
        if len(parts) < 2:
            return None
        roots.add(parts[0])
        saw_nested_entry = True

    return next(iter(roots)) if saw_nested_entry and len(roots) == 1 else None


def _destination_for(
    info: zipfile.ZipInfo,
    output_dir: Path,
    stripped_root: str | None,
) -> Path:
    parts = list(_safe_parts(info.filename))
    if stripped_root is not None and parts[0] == stripped_root:
        parts.pop(0)

    if not parts:
        raise ArchiveError(f"ZIP entry has no usable name: {info.filename!r}")

    destination = output_dir.joinpath(*parts)

    # Defence in depth: ensure platform-specific path handling cannot escape output.
    output_resolved = output_dir.resolve()
    destination_resolved = destination.resolve()
    if os.path.commonpath((output_resolved, destination_resolved)) != str(output_resolved):
        raise ArchiveError(f"ZIP path escapes the destination: {info.filename!r}")

    return destination


def _same_stream(info: zipfile.ZipInfo, source: BinaryIO, destination: Path) -> bool:
    if not destination.is_file() or destination.stat().st_size != info.file_size:
        return False
    with destination.open("rb") as existing:
        while True:
            source_chunk = source.read(1024 * 1024)
            existing_chunk = existing.read(1024 * 1024)
            if source_chunk != existing_chunk:
                return False
            if not source_chunk:
                return True


def _same_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path
) -> bool:
    with archive.open(info, "r") as source:
        return _same_stream(info, source, destination)


def _renamed_candidate(destination: Path, index: int) -> Path:
    return destination.with_name(f"{destination.stem} ({index}){destination.suffix}")


def _signature(info: zipfile.ZipInfo) -> tuple[int, int]:
    return info.file_size, info.CRC


def _choose_destination(
    *,
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    policy: ConflictPolicy,
    occupied: dict[str, tuple[int, int]],
    report: ExtractionReport,
) -> tuple[Path | None, str]:
    candidate = destination
    index = 2
    signature = _signature(info)
    while True:
        key = os.path.normcase(str(candidate.resolve()))
        planned_signature = occupied.get(key)

        if planned_signature is not None:
            if planned_signature == signature:
                report.identical += 1
                return None, "identical"
            conflict_exists = True
        else:
            conflict_exists = candidate.exists()
            if conflict_exists and candidate.is_file() and _same_member(
                archive, info, candidate
            ):
                report.identical += 1
                return None, "identical"

        if not conflict_exists:
            occupied[key] = signature
            action = "renamed" if candidate != destination else "extracted"
            return candidate, action

        if policy == "error":
            raise ConflictError(f"The file already exists: {candidate}")
        if policy == "skip":
            report.skipped += 1
            return None, "skipped"
        if policy == "overwrite":
            if candidate.is_dir():
                raise ConflictError(
                    f"Cannot replace a directory with a file: {candidate}"
                )
            occupied[key] = signature
            return candidate, "overwritten"

        candidate = _renamed_candidate(destination, index)
        index += 1


def _write_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None

    try:
        with archive.open(info, "r") as source, tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            shutil.copyfileobj(source, temporary)
        os.replace(temporary_name, destination)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def extract_archive(
    archive_path: Path,
    output_dir: Path = Path("data"),
    *,
    conflict: ConflictPolicy = "overwrite",
    keep_root: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    show_progress: bool = False,
    progress_callback: ExtractionProgress | None = None,
) -> ExtractionReport:
    """Extract an archive safely and return operation counters."""
    report = ExtractionReport()
    occupied: dict[str, tuple[int, int]] = {}

    with zipfile.ZipFile(archive_path, "r") as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        for info in entries:
            if _is_symlink(info):
                raise ArchiveError(
                    f"ZIP symbolic links are not supported: {info.filename!r}"
                )
            _safe_parts(info.filename)

        stripped_root = None if keep_root else _common_root(entries)

        total = len(entries)
        for position, info in enumerate(entries, start=1):
            destination = _destination_for(info, output_dir, stripped_root)
            selected, action = _choose_destination(
                archive=archive,
                info=info,
                destination=destination,
                policy=conflict,
                occupied=occupied,
                report=report,
            )

            if selected is None:
                if verbose:
                    print(f"{action:10} {destination}")
                elif show_progress:
                    _show_progress(position, total, action)
                if progress_callback is not None:
                    progress_callback(position, total, action, destination)
                continue

            if action == "renamed":
                report.renamed += 1
            elif action == "overwritten":
                report.overwritten += 1
            report.extracted += 1

            if verbose:
                print(f"{action:10} {selected}")
            if not dry_run:
                _write_member(archive, info, selected)
            if show_progress:
                _show_progress(position, total, action)
            if progress_callback is not None:
                progress_callback(position, total, action, selected)

    return report


def _show_progress(current: int, total: int, action: str) -> None:
    width = 28
    completed = width if total == 0 else round(width * current / total)
    bar = "█" * completed + "░" * (width - completed)
    print(f"\r[{bar}] {current}/{total} {action:<10}", end="", flush=True)
    if current == total:
        print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a ZIP archive faithfully into data/ without renaming its "
            "files or directories."
        )
    )
    parser.add_argument(
        "archive",
        type=Path,
        nargs="?",
        help="source ZIP archive (optional with --sync)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data"),
        help="destination directory (default: data)",
    )
    parser.add_argument(
        "--conflict",
        choices=("error", "skip", "overwrite", "rename"),
        default="overwrite",
        help=(
            "action when a name already contains different data "
            "(default: overwrite)"
        ),
    )
    parser.add_argument(
        "--keep-root",
        action="store_true",
        help="keep the common root directory from the ZIP archive",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="simulate extraction without writing files",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="then synchronize local .bin files to the Allmiibo over BLE",
    )
    parser.add_argument(
        "--device",
        help="exact device BLE name or address (default: first compatible device)",
    )
    parser.add_argument(
        "--drive",
        choices=("E", "I", "e", "i"),
        help="target drive (default: E when available, otherwise I)",
    )
    parser.add_argument(
        "--device-root",
        default="amiibo",
        help="target subdirectory on the device (default: amiibo)",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=15.0,
        help="maximum BLE scan duration in seconds (default: 15)",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=20.0,
        help="maximum idle time for a BLE response in seconds (default: 20)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.archive is None and not args.sync:
        parser.error("provide a ZIP archive or use --sync")
    if args.archive is not None and args.sync and args.dry_run:
        parser.error(
            "--dry-run with --sync requires synchronization only; "
            "prepare data/ first, then run again with --sync --dry-run"
        )
    if args.scan_timeout <= 0 or args.response_timeout <= 0:
        parser.error("timeouts must be strictly positive")
    clean_device_root = args.device_root.replace("\\", "/").strip("/")
    if not clean_device_root or ":" in clean_device_root:
        parser.error("--device-root must be a relative subdirectory, e.g. amiibo")

    if args.archive is not None:
        try:
            report = extract_archive(
                args.archive,
                args.output,
                conflict=args.conflict,
                keep_root=args.keep_root,
                dry_run=args.dry_run,
                verbose=args.verbose,
                show_progress=not args.verbose,
            )
        except (ArchiveError, ConflictError, OSError, zipfile.BadZipFile) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

        mode = "Simulation" if args.dry_run else "Preparation complete"
        print(
            f"{mode}: {report.extracted} file(s) processed, "
            f"{report.renamed} renamed after conflicts, "
            f"{report.overwritten} overwritten, "
            f"{report.identical} already identical, "
            f"{report.skipped} skipped."
        )

    if args.sync:
        try:
            from allmiibo_ble import AllmiiboError, sync_to_device

            print(
                "Scanning for the Allmiibo… Open Bluetooth Transmission on the "
                "device and close the website if it is connected."
            )
            device_name, remote_root, sync_report = asyncio.run(
                sync_to_device(
                    args.output,
                    selector=args.device,
                    drive=args.drive,
                    device_root=clean_device_root,
                    scan_timeout=args.scan_timeout,
                    response_timeout=args.response_timeout,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    show_progress=not args.verbose,
                )
            )
        except (AllmiiboError, OSError, ValueError) as error:
            print(f"Synchronization error: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("Synchronization interrupted.", file=sys.stderr)
            return 130

        mode = "BLE simulation" if args.dry_run else "Synchronization complete"
        print(
            f"{mode} with {device_name} to {remote_root}: "
            f"{sync_report.created} uploaded, "
            f"{sync_report.overwritten} overwritten, "
            f"{sync_report.identical} identical file(s) skipped, "
            f"{sync_report.folders_created} folder(s) created."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
