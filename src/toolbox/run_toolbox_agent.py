"""Run log-analysis test cases through Foundry toolbox skill resources.

This runner uses the toolbox MCP endpoint to discover attached skills with
``resources/list`` and load the selected skill with ``resources/read``. It does
not call the Foundry Skills download API or use the local skills cache.

Usage:
    python -m src.toolbox.run_toolbox_agent
    python -m src.toolbox.run_toolbox_agent --log sample_logs/web.log
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import APIStatusError


DEFAULT_TOOLBOX_NAME = "logs-analysis-toolbox"
DEFAULT_LOG_PATHS = ["sample_logs/web.log", "sample_logs/k8s.log"]
DEFAULT_AGENT_NAME = "logs-analysis-toolbox-agent"

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")


@dataclass(frozen=True)
class ToolboxSkillMetadata:
    name: str
    description: str
    uri: str


@dataclass(frozen=True)
class SkillDocument:
    name: str
    description: str
    instructions: str
    source_uri: str


def _read_text(path: Path, label: str) -> str:
    if not path.is_file():
        sys.exit(f"error: {label} not found at: {path}")
    return path.read_text(encoding="utf-8")


def _split_csv(values: str | list[str] | None, fallback: list[str]) -> list[str]:
    if values is None:
        return fallback

    raw_values = values if isinstance(values, list) else [values]
    parsed: list[str] = []
    for raw_value in raw_values:
        parsed.extend(value.strip() for value in raw_value.split(",") if value.strip())

    return parsed or fallback


def _build_toolbox_endpoint(project_endpoint: str, toolbox_name: str, version: str | None) -> str:
    # Use the default-version consumer endpoint unless a specific toolbox version is requested.
    base = project_endpoint.rstrip("/")
    if version:
        return f"{base}/toolboxes/{toolbox_name}/versions/{version}/mcp?api-version=v1"
    return f"{base}/toolboxes/{toolbox_name}/mcp?api-version=v1"


def _extract_text_content(result: Any) -> str:
    contents = getattr(result, "contents", None) or []
    text_parts: list[str] = []
    for item in contents:
        text = getattr(item, "text", None)
        if text is not None:
            text_parts.append(text)
    return "\n".join(text_parts).strip()


def _parse_skill_markdown(text: str, source_uri: str) -> SkillDocument:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{source_uri} must start with YAML frontmatter delimited by ---")

    try:
        close_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ValueError(f"{source_uri} is missing the closing --- frontmatter delimiter") from exc

    metadata = _parse_frontmatter(lines[1:close_index])
    instructions = "\n".join(lines[close_index + 1 :]).strip()
    name = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()

    if not name:
        raise ValueError(f"{source_uri} frontmatter must include name")
    if not _SKILL_NAME_RE.fullmatch(name):
        raise ValueError(f"{source_uri} skill name is invalid: {name}")
    if not description:
        raise ValueError(f"{source_uri} frontmatter must include description")
    if not instructions:
        raise ValueError(f"{source_uri} must include markdown instructions after frontmatter")

    return SkillDocument(
        name=name,
        description=description,
        instructions=instructions,
        source_uri=source_uri,
    )


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


def _build_analysis_instructions(skill: SkillDocument, toolbox_endpoint: str) -> str:
    return (
        "You are a log analysis assistant. Analyze a raw log file and produce a "
        "structured root-cause analysis. The application discovered Microsoft "
        "Foundry Skills from a toolbox MCP endpoint, selected the best matching "
        "skill from toolbox metadata, and loaded only that selected skill with "
        "resources/read. Follow this selected skill exactly.\n\n"
        "===== SELECTED TOOLBOX SKILL =====\n"
        f"Name: {skill.name}\n"
        f"Source: {skill.source_uri}\n"
        f"Toolbox endpoint: {toolbox_endpoint}\n"
        f"Description: {skill.description}\n\n"
        f"{skill.instructions}\n"
        "===== END SELECTED TOOLBOX SKILL ====="
    )


async def _load_toolbox_skill_index(toolbox_endpoint: str) -> list[ToolboxSkillMetadata]:
    # Connect as an MCP client and discover skills through toolbox resources.
    credential = DefaultAzureCredential()
    headers = {
        "Authorization": f"Bearer {credential.get_token('https://ai.azure.com/.default').token}",
        "Foundry-Features": "Toolboxes=V1Preview",
    }

    async with streamablehttp_client(toolbox_endpoint, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resources = await session.list_resources()
            print(f"\n=== Toolbox resources ({len(resources.resources)}) ===")
            for resource in resources.resources:
                print(f"  {resource.name}: {resource.uri}")

            # The SEP-2640 index advertises each skill without loading full instructions.
            index_resource = await session.read_resource("skill://index.json")
            index_text = _extract_text_content(index_resource)
            index = json.loads(index_text)
            skills = []
            for skill in index.get("skills", []):
                if skill.get("type") == "skill-md":
                    skills.append(
                        ToolboxSkillMetadata(
                            name=skill["name"],
                            description=skill.get("description", ""),
                            uri=skill["url"],
                        )
                    )
            return skills


async def _read_toolbox_skill(toolbox_endpoint: str, skill: ToolboxSkillMetadata) -> SkillDocument:
    # Load only the skill selected for this log; this is the toolbox equivalent of progressive disclosure.
    credential = DefaultAzureCredential()
    headers = {
        "Authorization": f"Bearer {credential.get_token('https://ai.azure.com/.default').token}",
        "Foundry-Features": "Toolboxes=V1Preview",
    }

    async with streamablehttp_client(toolbox_endpoint, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            skill_resource = await session.read_resource(skill.uri)
            skill_text = _extract_text_content(skill_resource)
            return _parse_skill_markdown(skill_text, skill.uri)


def _select_skill_from_toolbox_metadata(
    openai_client,
    model_deployment: str,
    log_text: str,
    skills: list[ToolboxSkillMetadata],
) -> ToolboxSkillMetadata:
    # Ask the model to route from names/descriptions only, before reading any SKILL.md body.
    skill_catalog = "\n".join(f"- {skill.name}: {skill.description}" for skill in skills)
    valid_names = {skill.name for skill in skills}
    log_excerpt = log_text[:12000]

    response = openai_client.responses.create(
        model=model_deployment,
        max_output_tokens=16,
        input=(
            "Choose the single best Microsoft Foundry toolbox skill for the log input. "
            "Use only the skill names and descriptions below. Reply with only "
            "the selected skill name and no extra text.\n\n"
            "Available toolbox skill metadata:\n"
            f"{skill_catalog}\n\n"
            "Log input:\n"
            f"{log_excerpt}"
        ),
    )

    raw_selection = response.output_text.strip().splitlines()[0].strip().strip('`"\' ')
    selected_name = raw_selection if raw_selection in valid_names else None
    if selected_name is None:
        selected_name = next((name for name in valid_names if name in response.output_text), None)
    if selected_name is None:
        sys.exit(
            "error: unable to route log input to a toolbox skill. "
            f"Model response was: {response.output_text!r}"
        )

    print("\n=== Toolbox skill routing decision ===")
    print(f"Selected toolbox skill: {selected_name}")
    return next(skill for skill in skills if skill.name == selected_name)


def _run_one_log(
    project_client: AIProjectClient,
    toolbox_endpoint: str,
    model_deployment: str,
    agent_name: str,
    log_path: Path,
    skills: list[ToolboxSkillMetadata],
    selected_skill_name: str | None,
    max_output_tokens: int | None,
) -> None:
    log_text = _read_text(log_path, "log file")
    openai_client = project_client.get_openai_client()
    if selected_skill_name:
        # Optional test escape hatch: keep toolbox loading, but skip the extra routing model call.
        selected_skill = next((skill for skill in skills if skill.name == selected_skill_name), None)
        if selected_skill is None:
            available = ", ".join(skill.name for skill in skills)
            sys.exit(
                f"error: selected toolbox skill not found: {selected_skill_name}. "
                f"Available skills: {available}"
            )
        print("\n=== Toolbox skill routing decision ===")
        print(f"Selected toolbox skill: {selected_skill.name} (explicit)")
    else:
        selected_skill = _select_skill_from_toolbox_metadata(
            openai_client,
            model_deployment,
            log_text,
            skills,
        )
    # This read goes through the toolbox MCP endpoint, not project.beta.skills.download or local cache.
    skill_document = asyncio.run(_read_toolbox_skill(toolbox_endpoint, selected_skill))
    instructions = _build_analysis_instructions(skill_document, toolbox_endpoint)

    # Create a prompt-agent version scoped to the selected toolbox skill for this invocation.
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model_deployment,
            instructions=instructions,
        ),
    )
    # Invoke the prompt agent through the Foundry OpenAI-compatible Responses API.
    response_kwargs: dict[str, Any] = {
        "input": f"Analyze the following log file:\n\n{log_text}",
        "extra_body": {"agent_reference": {"name": agent.name, "type": "agent_reference"}},
    }
    if max_output_tokens:
        response_kwargs["max_output_tokens"] = max_output_tokens
    response = openai_client.responses.create(**response_kwargs)

    print(f"\n=== Toolbox root-cause analysis ({model_deployment} / {log_path}) ===\n")
    print(response.output_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoke log root-cause analysis through toolbox skill resources.",
    )
    parser.add_argument(
        "--log",
        action="append",
        help=(
            "Path to a log file to analyze. Can be repeated or comma-separated. "
            "Defaults to sample_logs/web.log and sample_logs/k8s.log."
        ),
    )
    parser.add_argument(
        "--toolbox-name",
        default=os.environ.get("FOUNDRY_TOOLBOX_NAME", DEFAULT_TOOLBOX_NAME),
        help="Foundry toolbox name to consume.",
    )
    parser.add_argument(
        "--toolbox-version",
        help="Optional toolbox version to test. Defaults to the toolbox default version.",
    )
    parser.add_argument(
        "--agent-name",
        default=os.environ.get("TOOLBOX_AGENT_NAME", DEFAULT_AGENT_NAME),
        help="Name of the prompt agent to create/invoke for toolbox tests.",
    )
    parser.add_argument(
        "--selected-skill",
        help="Explicit toolbox skill name to use instead of spending a model call on routing.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help="Optional response output-token cap for the analysis model call.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=True)
    args = parse_args()

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    if not endpoint:
        sys.exit("error: FOUNDRY_PROJECT_ENDPOINT is not set. Copy .env.example to .env first.")
    if not model_deployment:
        sys.exit("error: MODEL_DEPLOYMENT_NAME is not set. Copy .env.example to .env first.")

    log_paths = [Path(value) for value in _split_csv(args.log, DEFAULT_LOG_PATHS)]
    toolbox_endpoint = _build_toolbox_endpoint(endpoint, args.toolbox_name, args.toolbox_version)

    try:
        # Load the toolbox skill catalog once, then reuse it for all requested logs.
        skills = asyncio.run(_load_toolbox_skill_index(toolbox_endpoint))
        if not skills:
            sys.exit("error: toolbox did not expose any skill resources.")

        print("\n=== Toolbox skill metadata ===")
        for skill in skills:
            print(f"  {skill.name}: {skill.description}")

        with AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
            allow_preview=True,
        ) as project_client:
            for log_path in log_paths:
                _run_one_log(
                    project_client,
                    toolbox_endpoint,
                    model_deployment,
                    args.agent_name,
                    log_path,
                    skills,
                    args.selected_skill,
                    args.max_output_tokens,
                )
    except HttpResponseError as exc:
        if exc.status_code in {401, 403}:
            sys.exit(
                "error: authentication/authorization failed. Ensure your identity has "
                "the Foundry User role on the Foundry project."
            )
        sys.exit(f"error: request failed: {exc.message}")
    except APIStatusError as exc:
        if exc.status_code == 401:
            sys.exit(
                "error: authentication failed (401). Ensure your identity has "
                "the Foundry User role on the Foundry project."
            )
        if exc.status_code == 429:
            sys.exit("error: model deployment rate limited (429). Wait and retry.")
        sys.exit(f"error: model request failed ({exc.status_code}): {exc.message}")
    except ValueError as exc:
        sys.exit(f"error: invalid toolbox skill content: {exc}")


if __name__ == "__main__":
    main()
