import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".spec", ".txt", ".yaml", ".yml"}
TEXT_NAMES = {".gitattributes", ".gitignore"}
EXCLUDED_DIRECTORIES = {".git", ".venv-build", "__pycache__", "build", "dist"}
ACCENTED_CODEPOINTS = {
    0x00C0,
    0x00C2,
    0x00C4,
    0x00C7,
    0x00C8,
    0x00C9,
    0x00CA,
    0x00CB,
    0x00CE,
    0x00CF,
    0x00D4,
    0x00D6,
    0x00D9,
    0x00DB,
    0x00DC,
    0x00E0,
    0x00E2,
    0x00E4,
    0x00E7,
    0x00E8,
    0x00E9,
    0x00EA,
    0x00EB,
    0x00EE,
    0x00EF,
    0x00F4,
    0x00F6,
    0x00F9,
    0x00FB,
    0x00FC,
    0x0152,
    0x0153,
    0x0178,
    0x00FF,
}
FORBIDDEN_WORDS = tuple(
    value[::-1]
    for value in (
        "ceva",
        "nucua",
        "enuacua",
        "euqehtoilibib",
        "nimehc",
        "reissod",
        "reihcif",
        "ehcrehcer",
        "egamonner",
        "noisserppus",
        "lierappa",
        "euqsid",
        "enicar",
        "rennoitceles",
        "retuoja",
        "remirppus",
        "remmoner",
        "resilautca",
        "regrahcelet",
        "elbinopsidni",
        "elbavuortni",
        "edilavni",
        "ajed",
        "tneviod",
        "tnevuep",
        "sruojuot",
        "etiusne",
        "tnadnep",
        "siuped",
        "euqsrol",
    )
)
FORBIDDEN_WORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(map(re.escape, FORBIDDEN_WORDS)) + r")\b",
    re.IGNORECASE,
)


class RepositoryLanguageTests(unittest.TestCase):
    def test_repository_owned_text_is_english_only(self) -> None:
        violations: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(ROOT).parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
                continue
            content = path.read_text(encoding="utf-8")
            if any(ord(character) in ACCENTED_CODEPOINTS for character in content):
                violations.append(f"{path.relative_to(ROOT)}: accented French character")
            match = FORBIDDEN_WORD_PATTERN.search(content)
            if match:
                violations.append(
                    f"{path.relative_to(ROOT)}: forbidden word {match.group(0)!r}"
                )

        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
