"""Utilities for the Foundry Skills direct-download demo."""

from __future__ import annotations

import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import SkillInlineContent


DEFAULT_SKILL_NAME = "web-logs-analysis"
DEFAULT_SKILL_DIR = Path("source") / "skills" / DEFAULT_SKILL_NAME
DEFAULT_SKILL_PATH = DEFAULT_SKILL_DIR / "SKILL.md"

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")


@dataclass(frozen=True)
class SkillDocument:
    """Parsed SKILL.md metadata and body."""

    name: str
    description: str
    instructions: str
    source_path: Path


def parse_skill_markdown(path: Path) -> SkillDocument:
    """Parse the required SKILL.md frontmatter using a small dependency-free parser."""
    text = _read_text(path)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} must start with YAML frontmatter delimited by ---")

    try:
        close_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ValueError(f"{path} is missing the closing --- frontmatter delimiter") from exc

    frontmatter = lines[1:close_index]
    instructions = "\n".join(lines[close_index + 1 :]).strip()
    metadata = _parse_frontmatter(frontmatter)

    name = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()
    if not name:
        raise ValueError(f"{path} frontmatter must include name")
    if not _SKILL_NAME_RE.fullmatch(name):
        raise ValueError(
            f"{path} skill name must match ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
        )
    if not description:
        raise ValueError(f"{path} frontmatter must include description")
    if not instructions:
        raise ValueError(f"{path} must include markdown instructions after frontmatter")

    return SkillDocument(
        name=name,
        description=description,
        instructions=instructions,
        source_path=path,
    )


def create_project_client(endpoint: str) -> AIProjectClient:
    """Create an AIProjectClient with preview APIs enabled for Skills."""
    return AIProjectClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def create_skill_package(skill_path: Path) -> bytes:
    """Create a ZIP package containing SKILL.md for the Foundry Skills API."""
    if not skill_path.is_file():
        raise FileNotFoundError(f"SKILL.md not found at {skill_path}")

    with tempfile.NamedTemporaryFile(suffix=".zip") as archive_file:
        with zipfile.ZipFile(archive_file.name, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(skill_path, arcname="SKILL.md")
        return Path(archive_file.name).read_bytes()


def extract_skill_package(chunks: Iterable[bytes], destination_dir: Path) -> Path:
    """Extract a downloaded skill ZIP and return the written SKILL.md path."""
    archive_bytes = b"".join(chunks)
    if not archive_bytes:
        raise ValueError("Downloaded skill package was empty")

    destination_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip") as archive_file:
        Path(archive_file.name).write_bytes(archive_bytes)
        with zipfile.ZipFile(archive_file.name) as archive:
            skill_members = [name for name in archive.namelist() if name.endswith("SKILL.md")]
            if not skill_members:
                raise ValueError("Downloaded skill package did not contain a SKILL.md")
            member = sorted(skill_members, key=len)[0]
            skill_text = archive.read(member).decode("utf-8")

    skill_path = destination_dir / "SKILL.md"
    skill_path.write_text(skill_text, encoding="utf-8")
    return skill_path


def publish_skill(project: AIProjectClient, skill_path: Path):
    """Publish a SKILL.md as a Foundry skill version.

    The azure-ai-projects 2.2.x preview API creates a new immutable skill version
    through ``create(name, inline_content=..., default=True)``. If the skill does
    not exist, the service creates it; if it exists, the service creates a new
    version and promotes it to default.
    """
    document = parse_skill_markdown(skill_path)
    return project.beta.skills.create(
        name=document.name,
        inline_content=SkillInlineContent(
            description=document.description,
            instructions=document.instructions,
        ),
        default=True,
    )


def download_skill(project: AIProjectClient, name: str, destination_dir: Path) -> Path:
    """Download the active Foundry skill package into a local skill directory."""
    if not hasattr(project.beta.skills, "download"):
        raise RuntimeError("This azure-ai-projects version does not expose beta.skills.download")
    return extract_skill_package(project.beta.skills.download(name), destination_dir)


def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if ":" not in line:
            raise ValueError(f"Unsupported frontmatter line: {line}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if value in {">", ">-"}:
            folded: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or not lines[index].strip()):
                stripped = lines[index].strip()
                if stripped:
                    folded.append(stripped)
                index += 1
            metadata[key] = " ".join(folded)
            continue

        if value.startswith(('"', "'")) or value.endswith(('"', "'")):
            raise ValueError(f"Frontmatter field {key} must be unquoted")
        metadata[key] = value
        index += 1

    return metadata


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")
