#!/usr/bin/env python3
"""Extract an Allmiibo ZIP archive into data/ and normalize .bin names."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable, Literal


BRACKET_PREFIX = re.compile(r"^\[[^\]\r\n]+\]\s*")
NUMBERED_PREFIX = re.compile(r"^[A-Za-z0-9]+\s+-\s+")
COMPACT_NUMBERED_PREFIX = re.compile(r"^\d{2,3}\s*-\s*")
UNDERSCORE_NUMBERED_PREFIX = re.compile(
    r"^[A-Za-z][A-Za-z0-9-]*_[A-Za-z]*\d+_-_(.+)$"
)
UNDERSCORE_GAME_PREFIX = re.compile(r"^[A-Z][A-Z0-9-]{1,7}_(.+)$")
LEGACY_BIN_PREFIX = re.compile(r"^\[[^\]\r\n]+\]\s+.+?\s+-\s+")
WHITESPACE = re.compile(r"\s+")

DEVICE_PATH_LIMIT = 63
DEVICE_NAME_LIMIT = 47

DIRECTORY_ALIASES = {
    "Animal Crossing x Sanrio Series": "Sanrio",
    "Welcome amiibo Series": "Welcome amiibo",
    "Jikkyou Powerful Pro Baseball": "Power Pros",
    "Monster Hunter Rise": "MH Rise",
    "Monster Hunter Stories": "MH Stories",
    "Skylanders SuperChargers": "Skylanders",
    "Super Mario Bros. 30th Anniversary": "30th Anniversary",
    "Super Mario Cereal": "Cereal",
    "Super Mario Figures": "Figures",
    "The Legend of Zelda": "Zelda",
    "The Legend of Zelda 30th Anniversary": "30th Anniversary",
    "The Legend of Zelda Breath of the Wild": "BOTW",
    "The Legend of Zelda Link's Awakening": "Link's Awakening",
    "The Legend of Zelda Skyward Sword": "Skyward Sword",
    "The Legend of Zelda Twilight Princess": "Twilight Princess",
}

TEXT_REPLACEMENTS = {
    "The Legend of Zelda": "Zelda",
    "The Wind Waker": "Wind Waker",
}
ConflictPolicy = Literal["error", "skip", "overwrite", "rename"]


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
    normalized: int = 0
    shortened: int = 0
    legacy_removed: int = 0


def normalize_bin_name(filename: str) -> str:
    """Return a clean display name for the supported .bin naming schemes."""
    if not filename.lower().endswith(".bin"):
        return filename

    stem = filename[:-4]
    had_bracket = BRACKET_PREFIX.match(stem) is not None
    stem = BRACKET_PREFIX.sub("", stem, count=1)

    underscored = UNDERSCORE_NUMBERED_PREFIX.match(stem)
    if underscored:
        stem = underscored.group(1)
    elif had_bracket:
        stem = NUMBERED_PREFIX.sub("", stem, count=1)
    elif "_" in stem:
        game_prefixed = UNDERSCORE_GAME_PREFIX.match(stem)
        if game_prefixed:
            stem = game_prefixed.group(1)
    else:
        stem = COMPACT_NUMBERED_PREFIX.sub("", stem, count=1)

    stem = WHITESPACE.sub(" ", stem.replace("_", " ")).strip(" ._-")
    for source, replacement in TEXT_REPLACEMENTS.items():
        stem = stem.replace(source, replacement)
    if stem.isalpha() and stem.isupper():
        stem = stem.capitalize()
    return f"{stem}.bin" if stem else filename


def normalize_directory_name(name: str) -> str:
    normalized = WHITESPACE.sub(" ", name.replace("_", " ")).strip(" ._-")
    return DIRECTORY_ALIASES.get(normalized, normalized)


def _utf8_prefix(value: str, maximum_bytes: int) -> str:
    result = bytearray()
    for character in value:
        encoded = character.encode("utf-8")
        if len(result) + len(encoded) > maximum_bytes:
            break
        result.extend(encoded)
    return result.decode("utf-8")


def _shorten_readably(value: str, maximum_bytes: int, *, suffix: str = "") -> str:
    available = maximum_bytes - len(suffix.encode("utf-8"))
    if available < 1:
        raise ArchiveError(f"Impossible de raccourcir proprement {value!r}")

    prefix = _utf8_prefix(value, available).rstrip(" ._-")
    word_break = prefix.rfind(" ")
    if word_break >= max(4, len(prefix) // 2):
        prefix = prefix[:word_break].rstrip(" ._-")
    if not prefix:
        raise ArchiveError(f"Impossible de raccourcir proprement {value!r}")
    return prefix + suffix


def _fit_final_path(
    directories: list[str], filename: str, device_root: str
) -> tuple[list[str], str]:
    fitted_directories = [
        _shorten_readably(name, DEVICE_NAME_LIMIT)
        if len(name.encode("utf-8")) > DEVICE_NAME_LIMIT
        else name
        for name in directories
    ]

    suffix = Path(filename).suffix
    stem = filename[: -len(suffix)] if suffix else filename
    filename_limit = DEVICE_NAME_LIMIT
    prefix = f"E:/{device_root.strip('/')}/"
    directory_prefix = "/".join(fitted_directories)
    if directory_prefix:
        prefix += directory_prefix + "/"
    filename_limit = min(
        filename_limit,
        DEVICE_PATH_LIMIT - len(prefix.encode("utf-8")),
    )
    if filename_limit < len(suffix.encode("utf-8")) + 1:
        raise ArchiveError(
            "Arborescence trop profonde pour l'Allmiibo, même après les alias: "
            f"{prefix}{filename}"
        )
    if len(filename.encode("utf-8")) > filename_limit:
        filename = _shorten_readably(stem, filename_limit, suffix=suffix)

    final_path = prefix + filename
    if len(final_path.encode("utf-8")) > DEVICE_PATH_LIMIT:
        raise ArchiveError(f"Chemin Allmiibo encore trop long: {final_path}")
    return fitted_directories, filename


def _safe_parts(member_name: str) -> tuple[str, ...]:
    if "\\" in member_name:
        raise ArchiveError(f"Chemin ZIP non sûr (antislash): {member_name!r}")

    path = PurePosixPath(member_name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ArchiveError(f"Chemin ZIP non sûr: {member_name!r}")

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
    device_root: str,
) -> tuple[Path, bool, bool]:
    parts = list(_safe_parts(info.filename))
    if stripped_root is not None and parts[0] == stripped_root:
        parts.pop(0)

    if not parts:
        raise ArchiveError(f"Entrée ZIP sans nom exploitable: {info.filename!r}")

    source_filename = parts[-1]
    normalized_filename = normalize_bin_name(source_filename)
    normalized_directories = [normalize_directory_name(part) for part in parts[:-1]]
    final_directories, final_filename = _fit_final_path(
        normalized_directories, normalized_filename, device_root
    )
    destination = output_dir.joinpath(*final_directories, final_filename)

    # Defence in depth: ensure platform-specific path handling cannot escape output.
    output_resolved = output_dir.resolve()
    destination_resolved = destination.resolve()
    if os.path.commonpath((output_resolved, destination_resolved)) != str(output_resolved):
        raise ArchiveError(f"Chemin ZIP hors de la destination: {info.filename!r}")

    normalized = normalized_filename != source_filename
    shortened = final_directories != parts[:-1] or final_filename != normalized_filename
    return destination, normalized, shortened


def _legacy_destination(
    info: zipfile.ZipInfo, output_dir: Path, stripped_root: str | None
) -> Path:
    parts = list(_safe_parts(info.filename))
    if stripped_root is not None and parts[0] == stripped_root:
        parts.pop(0)
    if parts[-1].lower().endswith(".bin"):
        parts[-1] = LEGACY_BIN_PREFIX.sub("", parts[-1], count=1) or parts[-1]
    return output_dir.joinpath(*parts)


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
    archive_collision = False

    while True:
        key = os.path.normcase(str(candidate.resolve()))
        planned_signature = occupied.get(key)

        if planned_signature is not None:
            if planned_signature == signature:
                report.identical += 1
                return None, "identique"
            conflict_exists = True
            archive_collision = True
        else:
            conflict_exists = candidate.exists()
            if conflict_exists and candidate.is_file() and _same_member(
                archive, info, candidate
            ):
                report.identical += 1
                return None, "identique"

        if not conflict_exists:
            occupied[key] = signature
            action = "renommé" if candidate != destination else "extrait"
            return candidate, action

        if policy == "error":
            raise ConflictError(f"Le fichier existe déjà: {candidate}")
        if policy == "skip":
            report.skipped += 1
            return None, "ignoré"
        if policy == "overwrite":
            if archive_collision:
                candidate = _renamed_candidate(destination, index)
                index += 1
                continue
            if candidate.is_dir():
                raise ConflictError(
                    f"Impossible de remplacer un dossier par un fichier: {candidate}"
                )
            occupied[key] = signature
            return candidate, "remplacé"

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
    device_root: str = "amiibo",
    dry_run: bool = False,
    verbose: bool = False,
    show_progress: bool = False,
) -> ExtractionReport:
    """Extract an archive safely and return operation counters."""
    report = ExtractionReport()
    occupied: dict[str, tuple[int, int]] = {}

    with zipfile.ZipFile(archive_path, "r") as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        for info in entries:
            if _is_symlink(info):
                raise ArchiveError(
                    f"Lien symbolique ZIP non pris en charge: {info.filename!r}"
                )
            _safe_parts(info.filename)

        stripped_root = None if keep_root else _common_root(entries)

        total = len(entries)
        migrations: list[tuple[zipfile.ZipInfo, Path, Path]] = []
        for position, info in enumerate(entries, start=1):
            destination, normalized, shortened = _destination_for(
                info, output_dir, stripped_root, device_root
            )
            report.normalized += int(normalized)
            report.shortened += int(shortened)
            migrations.append(
                (
                    info,
                    _legacy_destination(info, output_dir, stripped_root),
                    destination,
                )
            )
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
                    _show_progress(
                        position, total, "raccourci" if shortened else action
                    )
                continue

            if action == "renommé":
                report.renamed += 1
            elif action == "remplacé":
                report.overwritten += 1
            report.extracted += 1

            if verbose:
                label = "raccourci" if shortened else action
                print(f"{label:10} {selected}")
            if not dry_run:
                _write_member(archive, info, selected)
            if show_progress:
                _show_progress(position, total, "raccourci" if shortened else action)

        if not dry_run:
            for info, legacy, final in migrations:
                if legacy == final or not legacy.is_file():
                    continue
                if _same_member(archive, info, legacy):
                    legacy.unlink()
                    report.legacy_removed += 1
            for directory in sorted(
                (path for path in output_dir.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass

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
            "Extrait un ZIP vers data/ et retire les préfixes "
            "'[JEU] identifiant - ' des fichiers .bin."
        )
    )
    parser.add_argument(
        "archive",
        type=Path,
        nargs="?",
        help="archive ZIP source (facultative avec --sync)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data"),
        help="dossier de destination (défaut: data)",
    )
    parser.add_argument(
        "--conflict",
        choices=("error", "skip", "overwrite", "rename"),
        default="overwrite",
        help=(
            "action si un nom contient déjà des données différentes "
            "(défaut: overwrite)"
        ),
    )
    parser.add_argument(
        "--keep-root",
        action="store_true",
        help="conserve le dossier racine commun présent dans le ZIP",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="simule l'extraction sans écrire de fichier",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="synchronise ensuite les .bin locaux vers l'Allmiibo en BLE",
    )
    parser.add_argument(
        "--device",
        help="nom ou adresse BLE exacte de l'appareil (défaut: premier compatible)",
    )
    parser.add_argument(
        "--drive",
        choices=("E", "I", "e", "i"),
        help="disque cible (défaut: E si disponible, sinon I)",
    )
    parser.add_argument(
        "--device-root",
        default="amiibo",
        help="sous-dossier cible sur l'appareil (défaut: amiibo)",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=15.0,
        help="durée maximale de recherche BLE en secondes (défaut: 15)",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=20.0,
        help="inactivité maximale d'une réponse BLE en secondes (défaut: 20)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.archive is None and not args.sync:
        parser.error("indiquer une archive ZIP ou utiliser --sync")
    if args.archive is not None and args.sync and args.dry_run:
        parser.error(
            "--dry-run avec --sync nécessite une synchronisation seule; "
            "préparer d'abord data/, puis relancer avec --sync --dry-run"
        )
    if args.scan_timeout <= 0 or args.response_timeout <= 0:
        parser.error("les délais doivent être strictement positifs")
    clean_device_root = args.device_root.replace("\\", "/").strip("/")
    if not clean_device_root or ":" in clean_device_root:
        parser.error("--device-root doit être un sous-dossier relatif, ex. amiibo")

    if args.archive is not None:
        try:
            report = extract_archive(
                args.archive,
                args.output,
                conflict=args.conflict,
                keep_root=args.keep_root,
                device_root=clean_device_root,
                dry_run=args.dry_run,
                verbose=args.verbose,
                show_progress=not args.verbose,
            )
        except (ArchiveError, ConflictError, OSError, zipfile.BadZipFile) as error:
            print(f"Erreur: {error}", file=sys.stderr)
            return 1

        mode = "Simulation" if args.dry_run else "Préparation terminée"
        print(
            f"{mode}: {report.extracted} fichier(s) traité(s), "
            f"{report.renamed} renommé(s) pour conflit, "
            f"{report.overwritten} remplacé(s), "
            f"{report.identical} déjà identique(s), "
            f"{report.skipped} ignoré(s), "
            f"{report.normalized} nom(s) normalisé(s), "
            f"{report.shortened} chemin(s) raccourci(s), "
            f"{report.legacy_removed} ancien(s) chemin(s) nettoyé(s)."
        )

    if args.sync:
        try:
            from allmiibo_ble import AllmiiboError, sync_to_device

            print(
                "Recherche de l'Allmiibo… Place-le dans Bluetooth Transmission "
                "et ferme le site Web s'il est connecté."
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
            print(f"Erreur de synchronisation: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("Synchronisation interrompue.", file=sys.stderr)
            return 130

        mode = "Simulation BLE" if args.dry_run else "Synchronisation terminée"
        print(
            f"{mode} avec {device_name} vers {remote_root}: "
            f"{sync_report.created} envoyé(s), "
            f"{sync_report.overwritten} remplacé(s), "
            f"{sync_report.identical} identique(s) ignoré(s), "
            f"{sync_report.folders_created} dossier(s) créé(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
