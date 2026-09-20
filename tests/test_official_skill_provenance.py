from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PINNED_FILES = {
    REPO_ROOT / ".codex" / "skills" / "typesafe-ai" / "SKILL.md": (
        "71ea90d7906c6554c4f4c460ef7361b2d26f59116ccdae986dc6d997b9389f52"
    ),
    REPO_ROOT / ".codex" / "skills" / "typesafe-ai" / "LICENSE": (
        "835f233f1d6ed84a9b9a351aba0689b47644a4137d6316911fc7957bde523b02"
    ),
}


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def parse_minimal_front_matter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        raise ValueError("Content does not start with front matter delimiter '---'")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Malformed front matter in content")
    fm_text = parts[1]
    result: dict[str, str] = {}
    current_key: str | None = None
    accumulated_lines: list[str] = []

    for line in fm_text.splitlines():
        # Match top-level YAML key
        match = re.match(r"^([a-zA-Z0-9_-]+):(?:\s*(.*))?$", line)
        if match:
            if current_key is not None:
                result[current_key] = " ".join(accumulated_lines).strip()
            current_key = match.group(1)
            val = match.group(2)
            if val is not None and val.strip() not in (">", "|", ""):
                accumulated_lines = [val.strip()]
            else:
                accumulated_lines = []
        elif current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            accumulated_lines.append(line.strip())

    if current_key is not None:
        result[current_key] = " ".join(accumulated_lines).strip()

    return result


def test_vendored_typesafe_files_exist_and_hashes_match():
    for path, expected_hash in PINNED_FILES.items():
        assert path.is_file(), f"Expected vendored file does not exist: {path.name}"
        assert compute_sha256(path) == expected_hash, f"Hash mismatch for {path.name}"


def test_typesafe_skill_has_valid_front_matter():
    skill_path = REPO_ROOT / ".codex" / "skills" / "typesafe-ai" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    fm = parse_minimal_front_matter(content)

    assert "name" in fm and fm["name"], "SKILL.md front matter missing 'name'"
    assert "description" in fm and fm["description"], "SKILL.md front matter missing 'description'"
    assert fm["name"] == "typesafe-ai"


def test_vendored_files_contain_no_credentials_or_absolute_paths():
    secret_patterns = [
        re.compile(r"apikey_[a-zA-Z0-9_-]{8,}", re.IGNORECASE),
        re.compile(r"\b[0-9a-fA-F]{32,64}\b"),
    ]
    # Check for absolute paths like /Users/..., /home/..., C:\...
    abs_path_patterns = [
        re.compile(r"/Users/[a-zA-Z0-9._-]+"),
        re.compile(r"/home/[a-zA-Z0-9._-]+"),
        re.compile(r"[a-zA-Z]:\\"),
    ]

    typesafe_dir = REPO_ROOT / ".codex" / "skills" / "typesafe-ai"
    for path in (typesafe_dir / "SKILL.md", typesafe_dir / "LICENSE"):
        text = path.read_text(encoding="utf-8")
        for pat in secret_patterns:
            matches = pat.findall(text)
            assert not matches, f"Possible secret pattern found in {path.name}: {matches}"
        for pat in abs_path_patterns:
            matches = pat.findall(text)
            assert not matches, f"Absolute local path found in {path.name}: {matches}"


def test_mit_license_present_in_license_file():
    license_path = REPO_ROOT / ".codex" / "skills" / "typesafe-ai" / "LICENSE"
    content = license_path.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "Copyright" in content
    assert "Permission is hereby granted, free of charge" in content
