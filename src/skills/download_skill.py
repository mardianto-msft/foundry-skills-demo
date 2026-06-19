"""Download the active Microsoft Foundry Skill into the local skills directory.

Usage:
    python -m src.skills.download_skill --name web-logs-analysis
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from azure.core.exceptions import HttpResponseError
from dotenv import load_dotenv

from src.skills.foundry_skills import (
    DEFAULT_SKILL_DIR,
    DEFAULT_SKILL_NAME,
    create_project_client,
    download_skill,
    parse_skill_markdown,
)


DEFAULT_SKILL_NAMES = [DEFAULT_SKILL_NAME, "k8s-logs-analysis"]


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
        description="Download the active Foundry skill package into skills/<name>/SKILL.md.",
    )
    parser.add_argument(
        "--name",
        action="append",
        help=(
            "Foundry skill name to download. Can be repeated or comma-separated. "
            "Defaults to FOUNDRY_SKILL_NAMES, or the built-in two-skill demo."
        ),
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("SKILL_DIR"),
        help=(
            "Destination skill directory for single-skill downloads. For multiple "
            "skills, each skill is written to skills/<name>/SKILL.md."
        ),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        sys.exit("error: FOUNDRY_PROJECT_ENDPOINT is not set. Copy .env.example to .env first.")

    skill_names = _split_csv(
        args.name,
        _split_csv(os.environ.get("FOUNDRY_SKILL_NAMES"), DEFAULT_SKILL_NAMES),
    )

    try:
        with create_project_client(endpoint) as project:
            for name in skill_names:
                destination = Path(args.out) if args.out and len(skill_names) == 1 else Path("skills") / name
                skill_path = download_skill(project, name, destination)

                document = parse_skill_markdown(skill_path)
                print(f"Downloaded Foundry skill: {document.name}")
                print(f"Wrote: {skill_path}")
                print(f"Description: {document.description}")
    except HttpResponseError as exc:
        _exit_for_http_error(exc, ",".join(skill_names))


def _exit_for_http_error(exc: HttpResponseError, name: str) -> None:
    if exc.status_code == 404:
        sys.exit(f"error: Foundry skill not found: {name}. Publish it first.")
    if exc.status_code in {401, 403}:
        sys.exit(
            "error: authentication/authorization failed. Ensure your identity has "
            "the Foundry User role on the Foundry project."
        )
    sys.exit(f"error: failed to download skill: {exc.message}")


if __name__ == "__main__":
    main()
