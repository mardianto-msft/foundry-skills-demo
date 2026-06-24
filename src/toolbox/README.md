# Foundry Toolbox Flow

This folder contains the toolbox-based counterpart to the direct-download demo in
`src/agent` and `src/skills`.

The direct-download runner downloads one selected `SKILL.md` and injects it into
a prompt agent. The toolbox flow does not download skill content locally. It
creates a Foundry toolbox version that references already-published Foundry
skills, so MCP clients that support resources can discover the skill metadata and
read the full skill bodies from the toolbox endpoint at runtime.

## Create a Toolbox Version

Publish the skills first:

```bash
python -m src.skills.publish_skill
```

Then create or update the toolbox version:

```bash
python -m src.toolbox.create_toolbox
```

By default, the script reads:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_SKILL_NAMES`
- `FOUNDRY_TOOLBOX_NAME`, defaulting to `logs-analysis-toolbox`

Use `--pin-default-versions` to lock each toolbox reference to the skill version
that is currently default. Without that flag, the toolbox references follow each
skill's active `default_version`.

```bash
python -m src.toolbox.create_toolbox --pin-default-versions
```

The script promotes the created toolbox version to the toolbox default unless you
pass `--no-set-default`.

## Run the Log Test Cases

After creating the toolbox, run the same web and Kubernetes sample logs through
the toolbox skill-resource path:

```bash
python -m src.toolbox.run_toolbox_agent
```

The runner connects to the toolbox MCP endpoint, lists resources, reads
`skill://index.json`, routes each log using the skill names and descriptions,
loads only the selected `skill://<name>/SKILL.md` resource, and invokes a prompt
agent with that selected skill body. It does not use the Foundry Skills download
API or the local `skills/` cache.

To run a single log:

```bash
python -m src.toolbox.run_toolbox_agent --log sample_logs/web.log
```

For known sample cases, you can bypass the model-routing call and still exercise
toolbox resource loading plus prompt-agent analysis:

```bash
python -m src.toolbox.run_toolbox_agent --log sample_logs/k8s.log --selected-skill k8s-logs-analysis
```

