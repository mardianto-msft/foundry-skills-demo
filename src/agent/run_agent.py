"""Run the GPT log root-cause prompt agent against a sample log file.

This script:
    1. Gets configured Foundry skill metadata and routes to one matching skill.
    2. Downloads only the selected active skill into skills/<skill-name>/.
    3. Loads a log file and the selected SKILL.md analysis instructions.
    4. Ensures a Foundry *prompt agent* exists whose instructions are the selected
        SKILL.md and whose model is the configured GPT deployment.
    5. Invokes the agent with the log contents and prints the structured
     root-cause analysis.

Authentication uses Entra ID via ``DefaultAzureCredential`` (managed identity in
Azure, developer credentials locally). No keys are ever read or stored.

Usage:
    python -m src.agent.run_agent --log sample_logs/web.log
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from dotenv import load_dotenv
from openai import APIStatusError

from src.skills.foundry_skills import (
    DEFAULT_SKILL_NAME,
    SkillDocument,
    download_skill,
    parse_skill_markdown,
)


DEFAULT_FOUNDRY_SKILL_NAMES = [DEFAULT_SKILL_NAME, "k8s-logs-analysis"]


@dataclass(frozen=True)
class FoundrySkillMetadata:
    """Minimal Foundry skill metadata used for routing before download."""

    name: str
    description: str
    default_version: str
    latest_version: str


def _read_text(path: Path, label: str) -> str:
    """Read a UTF-8 text file, exiting with a clear message if it is missing."""
    if not path.is_file():
        sys.exit(f"error: {label} not found at: {path}")
    return path.read_text(encoding="utf-8")


def _split_csv(values: str | list[str] | None, fallback: list[str]) -> list[str]:
    """Accept comma-separated env values and repeated CLI arguments."""
    if values is None:
        return fallback

    raw_values = values if isinstance(values, list) else [values]
    parsed: list[str] = []
    for raw_value in raw_values:
        parsed.extend(value.strip() for value in raw_value.split(",") if value.strip())

    return parsed or fallback


def _build_analysis_instructions(skill: SkillDocument) -> str:
    """Compose prompt agent instructions from the selected downloaded SKILL.md."""
    return (
        "You are a log analysis assistant. Analyze a raw log file and produce a "
        "structured root-cause analysis. The application already selected the "
        "best matching Microsoft Foundry Skill from project metadata and "
        "downloaded its active version. Follow this selected skill exactly.\n\n"
        "===== SELECTED FOUNDRY SKILL =====\n"
        f"Name: {skill.name}\n"
        f"Source: {skill.source_path}\n"
        f"Description: {skill.description}\n\n"
        f"{skill.instructions}\n"
        "===== END SELECTED FOUNDRY SKILL ====="
    )


def _print_available_foundry_skills(project_client: AIProjectClient) -> None:
    """Print every skill currently stored in the Foundry project."""
    skills = list(project_client.beta.skills.list())
    print(f"\n=== Available Foundry skills ({len(skills)}) ===")
    for skill in skills:
        default_version = getattr(skill, "default_version", None) or "unknown"
        print(f"  {skill.name} (default: {default_version})")


def _get_configured_skill_metadata(
    project_client: AIProjectClient,
    skill_names: list[str],
) -> list[FoundrySkillMetadata]:
    """Fetch metadata for the skills this demo allows the router to choose."""
    metadata: list[FoundrySkillMetadata] = []
    for name in skill_names:
        skill = project_client.beta.skills.get(name=name)
        metadata.append(
            FoundrySkillMetadata(
                name=skill.name,
                description=getattr(skill, "description", "") or "",
                default_version=str(getattr(skill, "default_version", "unknown") or "unknown"),
                latest_version=str(getattr(skill, "latest_version", "unknown") or "unknown"),
            )
        )

    print("\n=== Configured Foundry skill metadata ===")
    for skill in metadata:
        print(
            f"  {skill.name} "
            f"(default: {skill.default_version}, latest: {skill.latest_version})"
        )
        print(f"    {skill.description}")

    return metadata


def _select_skill_from_metadata(
    openai_client,
    model_deployment: str,
    log_text: str,
    skills: list[FoundrySkillMetadata],
) -> str:
    """Use skill metadata, not full instructions, to choose one skill."""
    skill_catalog = "\n".join(
        f"- {skill.name}: {skill.description}"
        for skill in skills
    )
    valid_names = {skill.name for skill in skills}
    log_excerpt = log_text[:12000]

    response = openai_client.responses.create(
        model=model_deployment,
        max_output_tokens=16,
        input=(
            "Choose the single best Microsoft Foundry Skill for the log input. "
            "Use only the skill names and descriptions below. Reply with only "
            "the selected skill name and no extra text.\n\n"
            "Available skill metadata:\n"
            f"{skill_catalog}\n\n"
            "Log input:\n"
            f"{log_excerpt}"
        ),
    )

    raw_selection = response.output_text.strip().splitlines()[0].strip().strip('`"\' ')
    if raw_selection in valid_names:
        selected = raw_selection
    else:
        selected = next((name for name in valid_names if name in response.output_text), None)

    if not selected:
        sys.exit(
            "error: unable to route log input to a Foundry skill. "
            f"Model response was: {response.output_text!r}"
        )

    print("\n=== Skill routing decision ===")
    print(f"Selected Foundry skill: {selected}")
    return selected


def _get_selected_skill_path(
    project_client: AIProjectClient,
    skill: FoundrySkillMetadata,
) -> Path:
    skill_dir = Path("skills") / skill.name / skill.default_version
    skill_path = skill_dir / "SKILL.md"

    # Foundry exposes the active version as skill.default_version; SKILL.md only
    # contains Agent Skills frontmatter. Cache by versioned folder so an existing
    # local SKILL.md is used only for the selected active Foundry version.
    if skill_path.is_file():
        try:
            cached_skill = parse_skill_markdown(skill_path)
        except (OSError, ValueError) as exc:
            print(f"Cached SKILL.md is invalid; refreshing {skill.name}: {exc}")
        else:
            if cached_skill.name == skill.name:
                print(
                    "Using cached Foundry skill: "
                    f"{skill.name} (default: {skill.default_version})"
                )
                return skill_path

            print(
                "Cached SKILL.md did not match selected skill name; "
                f"refreshing {skill.name}."
            )

    print(
        "Downloading selected Foundry skill: "
        f"{skill.name} (default: {skill.default_version})"
    )
    return download_skill(project_client, skill.name, skill_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoke the GPT log root-cause prompt agent.",
    )
    parser.add_argument(
        "--log",
        required=True,
        help="Path to the log file to analyze, e.g. sample_logs/web.log",
    )
    parser.add_argument(
        "--agent-name",
        default=os.environ.get("AGENT_NAME", "logs-analysis-agent"),
        help="Name of the prompt agent to create/invoke.",
    )
    parser.add_argument(
        "--foundry-skill-name",
        action="append",
        help=(
            "Foundry skill name to include in metadata routing. Can be repeated "
            "or comma-separated. Defaults to "
            "FOUNDRY_SKILL_NAMES, or the built-in two-skill demo."
        ),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()

    # .env is written by azd post-provision and contains the Foundry project endpoint.
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    if not endpoint:
        sys.exit(
            "error: FOUNDRY_PROJECT_ENDPOINT is not set. Copy .env.example to "
            ".env and populate it (see infra/provision.sh output)."
        )

    log_text = _read_text(Path(args.log), "log file")

    # These names define the candidate skills for metadata-based routing.
    foundry_skill_names = _split_csv(
        args.foundry_skill_name,
        _split_csv(os.environ.get("FOUNDRY_SKILL_NAMES"), DEFAULT_FOUNDRY_SKILL_NAMES),
    )

    try:
        with AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
            allow_preview=True,
        ) as project_client:
            _print_available_foundry_skills(project_client)
            openai_client = project_client.get_openai_client()

            skill_metadata = _get_configured_skill_metadata(project_client, foundry_skill_names)
            selected_skill_name = _select_skill_from_metadata(
                openai_client,
                model_deployment,
                log_text,
                skill_metadata,
            )
            selected_skill_metadata = next(
                skill for skill in skill_metadata if skill.name == selected_skill_name
            )
            skill_path = _get_selected_skill_path(project_client, selected_skill_metadata)

            skill_document = parse_skill_markdown(skill_path)
            instructions = _build_analysis_instructions(skill_document)

            # Create a prompt-agent version with only the selected skill instructions.
            agent = project_client.agents.create_version(
                agent_name=args.agent_name,
                definition=PromptAgentDefinition(
                    model=model_deployment,
                    instructions=instructions,
                ),
            )

            # Invoke the prompt agent via the Foundry OpenAI-compatible Responses API.
            response = openai_client.responses.create(
                input=f"Analyze the following log file:\n\n{log_text}",
                extra_body={
                    "agent_reference": {"name": agent.name, "type": "agent_reference"}
                },
            )

        print(f"\n=== Root-cause analysis ({model_deployment} / {args.log}) ===\n")
        print(response.output_text)
    except HttpResponseError as exc:
        if exc.status_code == 401:
            sys.exit(
                "error: authentication failed (401). Ensure your identity has "
                "the 'Foundry User' role on the Foundry project."
            )
        if exc.status_code == 429:
            sys.exit("error: rate limited (429). Wait and retry.")
        sys.exit(f"error: request failed: {exc.message}")
    except APIStatusError as exc:
        if exc.status_code == 401:
            sys.exit(
                "error: authentication failed (401). Ensure your identity has "
                "the 'Foundry User' role on the Foundry project."
            )
        if exc.status_code == 429:
            sys.exit("error: model deployment rate limited (429). Wait and retry.")
        sys.exit(f"error: model request failed ({exc.status_code}): {exc.message}")


if __name__ == "__main__":
    main()
