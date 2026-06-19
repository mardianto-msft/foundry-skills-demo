"""Publish the local web and Kubernetes SKILL.md files to Microsoft Foundry Skills.

Usage:
    python -m src.skills.publish_skill
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from azure.core.exceptions import HttpResponseError
from dotenv import load_dotenv

from src.skills.foundry_skills import (
    DEFAULT_SKILL_PATH,
    create_project_client,
    parse_skill_markdown,
    publish_skill,
)


DEFAULT_SKILL_PATHS = [
    str(DEFAULT_SKILL_PATH),
    "source/skills/k8s-logs-analysis/SKILL.md",
]


def _split_csv(values: str | list[str] | None, fallback: list[str]) -> list[str]:
    if values is None:
        return fallback

    raw_values = values if isinstance(values, list) else [values]
    parsed: list[str] = []
    for raw_value in raw_values:
        parsed.extend(value.strip() for value in raw_value.split(",") if value.strip())

    return parsed or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a local SKILL.md as a versioned Microsoft Foundry Skill.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        help=(
            "Path to a SKILL.md to publish. Can be repeated or comma-separated. "
            "Defaults to SOURCE_SKILL_PATHS/SKILL_PATHS, or the built-in source/skills demo."
        ),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        sys.exit("error: FOUNDRY_PROJECT_ENDPOINT is not set. Copy .env.example to .env first.")

    skill_paths = _split_csv(
        args.skill,
        _split_csv(
            os.environ.get("SOURCE_SKILL_PATHS") or os.environ.get("SKILL_PATHS"),
            DEFAULT_SKILL_PATHS,
        ),
    )

    try:
        with create_project_client(endpoint) as project:
            for skill_path_value in skill_paths:
                skill_path = Path(skill_path_value)
                document = parse_skill_markdown(skill_path)
                result = publish_skill(project, skill_path)

                version = getattr(result, "version", None) or result.get("version", "unknown")
                default_version = getattr(result, "default_version", None) or result.get(
                    "default_version", None
                )
                print(f"Published Foundry skill: {document.name}")
                print(f"Description: {document.description}")
                print(f"Version: {version}")
                if default_version:
                    print(f"Default version: {default_version}")
    except HttpResponseError as exc:
        _exit_for_http_error(exc)


def _exit_for_http_error(exc: HttpResponseError) -> None:
    if exc.status_code in {401, 403}:
        sys.exit(
            "error: authentication/authorization failed. Ensure your identity has "
            "the Foundry User role on the Foundry project."
        )
    sys.exit(f"error: failed to publish skill: {exc.message}")


if __name__ == "__main__":
    main()
