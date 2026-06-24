"""Create a Microsoft Foundry toolbox version that references published skills.

This is the toolbox/MCP-oriented counterpart to the direct-download demo. It does
not download SKILL.md files or modify the prompt-agent runner.

Usage:
    python -m src.toolbox.create_toolbox
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from dataclasses import dataclass
from typing import Any

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv


DEFAULT_TOOLBOX_NAME = "logs-analysis-toolbox"
DEFAULT_SKILL_NAMES = ["web-logs-analysis", "k8s-logs-analysis"]


@dataclass(frozen=True)
class SkillReference:
    """Foundry skill reference to attach to a toolbox version."""

    id: str
    name: str
    default_version: str


def _split_csv(values: str | list[str] | None, fallback: list[str]) -> list[str]:
    if values is None:
        return fallback

    raw_values = values if isinstance(values, list) else [values]
    parsed: list[str] = []
    for raw_value in raw_values:
        parsed.extend(value.strip() for value in raw_value.split(",") if value.strip())

    return parsed or fallback


def _model_value(model: Any, key: str, default: str = "") -> str:
    value = getattr(model, key, None)
    if value is None and hasattr(model, "get"):
        value = model.get(key, default)
    return str(value or default)


def _toolbox_skill_reference(skill: SkillReference, version: str | None) -> Any:
    """Build the skill-reference object accepted by the installed preview SDK.

    azure-ai-projects preview versions have used two shapes here:
    ``ToolboxSkillReference(name=...)`` in newer docs and
    ``SkillReferenceParam(skill_id=...)`` in older generated SDKs. Keep the
    compatibility shim local to the toolbox workflow so direct-download code is
    unaffected.
    """
    try:
        from azure.ai.projects.models import ToolboxSkillReference
    except ImportError:
        kwargs = {"type": "skill_reference", "name": skill.name}
        if version:
            kwargs["version"] = version
        return kwargs

    kwargs = {"name": skill.name}
    if version:
        kwargs["version"] = version
    return ToolboxSkillReference(**kwargs)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


def _create_project_client(endpoint: str) -> AIProjectClient:
    return AIProjectClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _create_toolbox_version(
    project,
    toolbox_name: str,
    description: str,
    skill_references: list[Any],
):
    if not hasattr(project.beta, "toolboxes"):
        raise RuntimeError(
            "This azure-ai-projects version does not expose beta.toolboxes. "
            "Upgrade azure-ai-projects to a version with toolbox preview APIs."
        )

    create_version = project.beta.toolboxes.create_version
    parameters = inspect.signature(create_version).parameters
    if "skills" in parameters:
        return create_version(
            name=toolbox_name,
            description=description,
            tools=[],
            skills=skill_references,
        )

    body = {
        "description": description,
        "tools": [],
        "skills": [_to_jsonable(reference) for reference in skill_references],
    }
    return create_version(name=toolbox_name, body=body)


def _set_default_toolbox_version(project, toolbox_name: str, version: str) -> None:
    project.beta.toolboxes.update(toolbox_name, default_version=version)


def _get_skill_references(project, skill_names: list[str]) -> list[SkillReference]:
    references: list[SkillReference] = []
    for name in skill_names:
        skill = project.beta.skills.get(name=name)
        references.append(
            SkillReference(
                id=_model_value(skill, "id"),
                name=_model_value(skill, "name", name),
                default_version=_model_value(skill, "default_version"),
            )
        )
    return references


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Foundry toolbox version that references published skills.",
    )
    parser.add_argument(
        "--toolbox-name",
        default=os.environ.get("FOUNDRY_TOOLBOX_NAME", DEFAULT_TOOLBOX_NAME),
        help="Foundry toolbox name to create/update.",
    )
    parser.add_argument(
        "--skill-name",
        action="append",
        help=(
            "Foundry skill name to attach. Can be repeated or comma-separated. "
            "Defaults to FOUNDRY_SKILL_NAMES, or the built-in two-skill demo."
        ),
    )
    parser.add_argument(
        "--description",
        default="Log root-cause analysis skills for MCP clients.",
        help="Human-readable description for the toolbox version.",
    )
    parser.add_argument(
        "--pin-default-versions",
        action="store_true",
        help="Pin each toolbox reference to the skill's current default version.",
    )
    parser.add_argument(
        "--no-set-default",
        action="store_true",
        help="Create the toolbox version without promoting it to the toolbox default.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        sys.exit("error: FOUNDRY_PROJECT_ENDPOINT is not set. Run azd up to generate .env, or create .env from infra/provision.sh output.")

    skill_names = _split_csv(
        args.skill_name,
        _split_csv(os.environ.get("FOUNDRY_SKILL_NAMES"), DEFAULT_SKILL_NAMES),
    )

    try:
        with _create_project_client(endpoint) as project:
            skill_metadata = _get_skill_references(project, skill_names)
            skill_references = [
                _toolbox_skill_reference(
                    skill,
                    skill.default_version if args.pin_default_versions else None,
                )
                for skill in skill_metadata
            ]

            toolbox_version = _create_toolbox_version(
                project,
                args.toolbox_name,
                args.description,
                skill_references,
            )
            version = str(getattr(toolbox_version, "version", "") or toolbox_version.get("version", ""))
            if not version:
                sys.exit("error: toolbox version creation did not return a version.")

            if not args.no_set_default:
                _set_default_toolbox_version(project, args.toolbox_name, version)

            print(f"Created Foundry toolbox: {args.toolbox_name}")
            print(f"Version: {version}")
            if not args.no_set_default:
                print(f"Default version: {version}")
            print("Attached skills:")
            for skill in skill_metadata:
                version_text = (
                    f" pinned to {skill.default_version}"
                    if args.pin_default_versions and skill.default_version
                    else " following skill default_version"
                )
                print(f"  {skill.name} ({version_text})")
    except HttpResponseError as exc:
        _exit_for_http_error(exc)
    except RuntimeError as exc:
        sys.exit(f"error: {exc}")


def _exit_for_http_error(exc: HttpResponseError) -> None:
    if exc.status_code == 404:
        sys.exit("error: Foundry skill or toolbox endpoint not found. Publish skills first.")
    if exc.status_code in {401, 403}:
        sys.exit(
            "error: authentication/authorization failed. Ensure your identity has "
            "the Foundry User role on the Foundry project."
        )
    sys.exit(f"error: failed to create toolbox: {exc.message}")


if __name__ == "__main__":
    main()
