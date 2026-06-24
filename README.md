# Foundry Skills — Log Root-Cause Analysis Demo

A Microsoft Foundry **prompt agent** demo that analyzes logs and returns a probable
**root cause** plus a **suggested solution**. The agent is powered by a GPT model
deployment (default `gpt-5.4`, version `2026-03-05`, region `eastus2`) and supports
two Microsoft Foundry Skills consumption methods side by side:

- **Direct download**: publish web and Kubernetes `SKILL.md` files as versioned
   Foundry skills, read Foundry skill metadata at run time, let the model select
   the best skill, download the selected active version when its versioned cache
   is missing, then inject only that selected `SKILL.md` into the prompt agent
   instructions.
- **Toolbox**: create a Foundry toolbox version that references the published
   skills, so MCP clients can discover and read skill resources from a toolbox
   endpoint without this demo downloading `SKILL.md` files locally.

The demo includes reproducible sample logs, with an optional generator for
creating fresh log data.

> **Preview notice:** Microsoft Foundry Skills and the related
> `azure-ai-projects` `project.beta.skills` APIs are in preview. SDK method names,
> request shapes, model behavior, or service requirements may change, and this
> demo code may need updates as the preview evolves. See
> [Use skills with Microsoft Foundry agents (preview)](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?pivots=python)
> for the official guidance.

## Architecture

Both methods start the same way: authored `SKILL.md` files are published to the
Foundry Skills API as versioned skills. The difference is how the runtime loads
the selected skill instructions.

In the **direct-download** method, `run_agent.py` reads Foundry skill metadata,
asks the model to choose one skill from names and descriptions, downloads the
selected active version into a local versioned cache when needed, and invokes the
prompt agent with only that selected `SKILL.md`.

In the **toolbox** method, `create_toolbox.py` creates a Foundry toolbox version
that references the published skills. `run_toolbox_agent.py` connects to the
toolbox MCP endpoint, lists skill resources, reads `skill://index.json`, asks the
model to choose one skill from toolbox metadata, loads only the selected
`skill://<name>/SKILL.md` resource, and invokes the prompt agent with that skill
body.

```mermaid
graph TD
   A[Source skills] --> B[Publish skills]
   B --> C[Foundry Skills API]
   L[Sample logs] --> D1[Direct runner]
   L --> T1[Toolbox runner]
   C --> DD[Method 1: Direct download]
   DD --> D2[Read skill metadata]
   D2 --> D3[Model chooses skill]
   D3 --> D4[Download selected skill]
   D4 --> D1
   C --> TB[Method 2: Toolbox]
   TB --> T2[Create toolbox]
   T2 --> T3[Toolbox MCP resources]
   T3 --> T4[Read skill index]
   T4 --> T5[Model chooses skill]
   T5 --> T6[Read selected skill]
   T6 --> T1
   D1 --> P[Prompt agent]
   T1 --> P
   P --> O[Root cause output]
```

## Project Structure

```
foundry-skills/
├── README.md
├── azure.yaml                  # azd deployment entry point
├── requirements.txt
├── infra/                      # Bicep + provisioning for the Foundry project
│   ├── main.bicep
│   ├── main.bicepparam
│   └── provision.sh            # Azure CLI fallback if not using azd
├── source/
│   └── skills/                 # Authored SKILL.md files published to Foundry
│       ├── web-logs-analysis/
│       │   └── SKILL.md
│       └── k8s-logs-analysis/
│           └── SKILL.md
├── skills/                     # Downloaded active Foundry skill cache
│   ├── web-logs-analysis/
│   │   └── v1/
│   │       └── SKILL.md
│   └── k8s-logs-analysis/
│       └── v1/
│           └── SKILL.md
├── src/
│   ├── log_generator/          # Generates realistic sample logs
│   ├── skills/                 # Publishes/downloads Foundry Skills
│   ├── toolbox/                # Creates and tests toolbox skill-resource flow
│   │   ├── create_toolbox.py
│   │   └── run_toolbox_agent.py
│   └── agent/
│       └── run_agent.py        # Runs the prompt agent against a log file
└── sample_logs/                # Generated sample logs (committed for offline demo)
    └── web.log
```

## Prerequisites

- An **Azure subscription**
- **Azure CLI** (`az`) — logged in via `az login`
- **Azure Developer CLI** (`azd`) for provisioning with `azd up`
- **Python 3.x**
- **uv** for creating the local Python virtual environment
- `azure-ai-projects >= 2.2.0` for the preview `project.beta.skills` and
   `project.beta.toolboxes` APIs
- `mcp` Python package for the toolbox MCP client test runner
- A **Microsoft Foundry project** provisioned by `azd up` or `infra/provision.sh`
- Azure RBAC for deployment and runtime access:
    - **Contributor** on the target subscription to let `azd up` create the
       resource group and deploy the Azure AI Services account, Foundry project,
       and model deployment. If the resource group already exists and the
       `Microsoft.CognitiveServices` provider is already registered, **Contributor**
       on that resource group is sufficient for the Bicep deployment.
    - **User Access Administrator** on the Foundry account, resource group, or
       subscription only if you will grant the runtime role yourself. This is the
       least-privilege built-in role for creating Azure RBAC role assignments.
    - **Foundry User** on the Foundry project, or inherited from the Foundry
       account, for publishing skills, creating toolboxes, and running agents.

> Region: **eastus2** &nbsp;•&nbsp; Default model: **gpt-5.4** (`2026-03-05`)

See the Appendix for model override commands, resource naming details, and Foundry
Skills preview SDK notes.

## Getting Started

Follow these steps from the repository root. Steps 1-5 are shared setup for both
the direct-download and toolbox methods. After publishing skills, choose one or
both runtime paths.

1. **Create a Python virtual environment and install dependencies**:

   ```bash
   uv venv .venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

2. **Sign in with Azure Developer CLI**:

   ```bash
   azd auth login
   ```

3. **Create an azd environment and choose a location**:

   ```bash
   azd env new
   ```

   Choose a short lowercase environment name such as `foundry-skills-demo` and
   select **East US 2** (`eastus2`) for the location.

4. **Provision the Foundry project and GPT model deployment**:

   ```bash
   azd up
   ```

   This deploys the Bicep infrastructure in [infra/main.bicep](infra/main.bicep):
   an Azure AI Services account, a Foundry project, and a GPT model
   deployment in the location you selected. Use `eastus2` unless you intentionally
   change the demo region. See the Appendix for naming details.

5. **Publish the local `SKILL.md` files as versioned Foundry Skills**:

   ```bash
   python -m src.skills.publish_skill
   ```

   This publishes both authored skills from `SOURCE_SKILL_PATHS`:
   - [`source/skills/web-logs-analysis/SKILL.md`](source/skills/web-logs-analysis/SKILL.md) for web/API logs
   - [`source/skills/k8s-logs-analysis/SKILL.md`](source/skills/k8s-logs-analysis/SKILL.md) for Kubernetes/container logs

   To publish only one source skill, pass `--skill source/skills/web-logs-analysis/SKILL.md` or
   `--skill source/skills/k8s-logs-analysis/SKILL.md`.

### Method 1: Direct Download

Use this method when you want the app to download the selected active skill
version into the local `skills/` cache and inject that downloaded `SKILL.md` into
the prompt agent instructions.

6. **Run the direct-download agent against a sample log**:

   ```bash
   python -m src.agent.run_agent --log sample_logs/web.log
   ```

   The runner first reads Foundry skill metadata with `project.beta.skills.get(...)`,
   asks the model to choose one skill from names/descriptions only, downloads the
   active version of that selected skill when the versioned local cache is missing,
   and then creates the prompt agent with only that downloaded `SKILL.md`. The
   response includes a `Selected Skill` section to show which skill was used for
   the input log.

7. **Try the other planted scenarios with direct download**:

   ```bash
   python -m src.agent.run_agent --log sample_logs/k8s.log
   python -m src.agent.run_agent --log sample_logs/mixed.log
   ```

### Method 2: Toolbox

Use this method when you want the skills to stay behind a Foundry toolbox MCP
endpoint. The runner discovers skills as MCP resources and reads only the
selected `skill://<name>/SKILL.md` resource.

6. **Create a toolbox version with skill references**:

   ```bash
   python -m src.toolbox.create_toolbox
   ```

   This separate flow attaches the published skills from `FOUNDRY_SKILL_NAMES` to
   a Foundry toolbox named by `FOUNDRY_TOOLBOX_NAME` or `logs-analysis-toolbox`.
   It does not change the direct-download runner. By default, toolbox skill
   references follow each skill's active `default_version`; pass
   `--pin-default-versions` to pin the references to the versions that are
   currently active.

   ```bash
   python -m src.toolbox.create_toolbox --pin-default-versions
   ```

7. **Run the toolbox test runner against the web and Kubernetes sample logs**:

   ```bash
   python -m src.toolbox.run_toolbox_agent
   ```

   The runner connects to the toolbox MCP endpoint, calls `resources/list`, reads
   `skill://index.json`, asks the model to select one skill from toolbox skill
   names and descriptions, reads only the selected `skill://<name>/SKILL.md`, and
   invokes the prompt agent with that selected skill body.

8. **Run a single toolbox sample or bypass routing for known cases**:

   ```bash
   python -m src.toolbox.run_toolbox_agent --log sample_logs/web.log
   python -m src.toolbox.run_toolbox_agent --log sample_logs/k8s.log --selected-skill k8s-logs-analysis
   ```

   `--selected-skill` is a test convenience for known scenarios or rate-limit
   recovery. It still loads the skill through toolbox `resources/read`, but skips
   the model call that chooses the skill.

## Direct-Download Flow

The agent's reasoning is driven by Skills defined in
[`source/skills/web-logs-analysis/SKILL.md`](source/skills/web-logs-analysis/SKILL.md) and
[`source/skills/k8s-logs-analysis/SKILL.md`](source/skills/k8s-logs-analysis/SKILL.md). In this
direct-download mode, the skills are first stored centrally in Foundry through the
Skills API. At run time, `run_agent.py` gets the configured skill metadata from
Foundry, routes the log to one skill using only the skill names and descriptions,
downloads the active version of that selected skill into
`skills/<skill-name>/<default-version>/`, and injects only that downloaded
`SKILL.md` into the prompt agent's instructions for the analysis session.

If the selected skill's active Foundry default version is already downloaded, the
runner reuses `skills/<skill-name>/<default-version>/SKILL.md`.

That means the demo exercises the Foundry Skills lifecycle enough to show the value of
versioned behavior: update a `SKILL.md`, publish a new Foundry skill version,
download the active version, and rerun the agent without changing the agent code.

## Toolbox Flow

The separate toolbox implementation lives in [src/toolbox](src/toolbox). It uses
the same published Foundry skills as the direct-download flow, but it creates a
toolbox version with skill references instead of downloading skill content. MCP
clients that support resources can connect to the toolbox endpoint, discover the
attached skill resources, and read the full skill bodies on demand.

The toolbox runner follows the progressive-disclosure pattern from the toolbox
MCP endpoint:

1. Connect to the toolbox MCP endpoint with the
   `Foundry-Features: Toolboxes=V1Preview` header.
2. Call `resources/list` to verify the attached skill resources.
3. Read `skill://index.json` for skill names, descriptions, and `SKILL.md` URIs.
4. Ask the model to choose one skill using only the toolbox skill metadata.
5. Read only the selected `skill://<name>/SKILL.md` resource.
6. Create and invoke a prompt agent with that selected skill body.

Run it after publishing skills:

```bash
python -m src.toolbox.create_toolbox
```

Useful options:

- `--toolbox-name <name>` overrides `FOUNDRY_TOOLBOX_NAME`.
- `--skill-name <name>` attaches one or more explicit skill names.
- `--pin-default-versions` pins each reference to the current skill default.
- `--no-set-default` creates the toolbox version without promoting it to default.

To run the web and Kubernetes sample logs through the toolbox resource path:

```bash
python -m src.toolbox.run_toolbox_agent
```

This test runner uses the toolbox MCP endpoint to list skill resources, reads the
selected `skill://<name>/SKILL.md` resource, and invokes a prompt agent with that
selected skill body. It does not use the direct-download cache.

For known sample cases, pass `--selected-skill <name>` to skip the model-routing
call while still testing toolbox `resources/read` and analysis with the selected
skill.

## Troubleshooting

### Model Deployment Rate Limited (429)

If an agent run fails with a model deployment rate-limit error such as HTTP 429,
increase the model deployment TPM capacity before reprovisioning. The deployment
capacity is configured in [infra/main.bicepparam](infra/main.bicepparam) with the
`AZURE_AI_DEPLOYMENT_CAPACITY` environment variable, which maps to
`deploymentCapacity` in [infra/main.bicep](infra/main.bicep). The value is in
thousands of tokens per minute (TPM).

For example, to raise the deployment to 50k TPM:

```bash
azd env set AZURE_AI_DEPLOYMENT_CAPACITY 50
azd up
```

If quota is still insufficient in the selected region or SKU, request more Azure
OpenAI quota or choose a region/SKU with available capacity, then rerun `azd up`.

## Appendix

### Azure Resource Naming

The azd environment name is exposed as `AZURE_ENV_NAME`. The [azure.yaml](azure.yaml)
pre-provision hook sets the resource group name to `rg-<env name>`. For example,
environment `foundry-skills-demo` deploys to `rg-foundry-skills-demo`.

Foundry resources also derive from the environment name:

- Foundry account: `aif-<env name>-<4-char suffix>`
- Foundry project: `aif-proj`

For example, environment `foundry-skills-demo` creates a Foundry account like
`aif-foundry-skills-demo-ab12` and project `aif-proj`.

### azd Outputs

The [infra/main.bicep](infra/main.bicep) deployment exports the values the Python
scripts read, including:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ENDPOINT`
- `MODEL_DEPLOYMENT_NAME`
- `AZURE_REGION`
- `FOUNDRY_SKILL_NAMES`
- `FOUNDRY_TOOLBOX_NAME`
- `SOURCE_SKILL_PATHS`
- `AGENT_NAME`

### Refresh `.env` Manually

`azd up` runs [infra/post-provision.sh](infra/post-provision.sh), which writes the
latest azd outputs into `.env` automatically. If you need to refresh `.env`
manually, run:

```bash
azd env get-values > .env
```

Prefer Azure CLI instead of azd? Run `./infra/provision.sh` and copy the printed
values into `.env`.

### Verify the Foundry SDK Version

The demo expects `azure-ai-projects` 2.2.0 or later for the preview
`project.beta.skills` APIs. To verify the installed version:

```bash
python - <<'PY'
import azure.ai.projects as projects
print(projects.__version__)
PY
```

### Generate New Sample Logs

The demo includes prebuilt logs under `sample_logs/`, so this step is optional.
To regenerate deterministic sample logs, run:

```bash
python -m src.log_generator.generate --scenario all --seed 42 --out sample_logs
```

This writes `sample_logs/web.log`, `sample_logs/k8s.log`, `sample_logs/mixed.log`,
and matching `.expected.json` ground-truth files.

### Download Skills Manually

The normal `run_agent.py` flow reads Foundry skill metadata, selects one skill, and
downloads only the selected active version automatically. To download all configured
skills into the local cache for inspection, run:

```bash
python -m src.skills.download_skill
```

The downloaded packages are written to `skills/<skill-name>/SKILL.md` for manual
inspection. The normal runner uses versioned cache folders under
`skills/<skill-name>/<default-version>/`.

### Model Version Notes

The default deployment is `gpt-5.4` in `eastus2` with model version `2026-03-05`.

To list available model names and versions for a region:

```bash
az cognitiveservices model list \
   --location eastus2 \
   --query "[].{name:model.name, version:model.version, format:model.format, default:model.isDefaultVersion}" \
   -o table
```

To override the model deployment values before running `azd up`:

```bash
azd env set MODEL_DEPLOYMENT_NAME <model-name>
azd env set AZURE_AI_MODEL_NAME <model-name>
azd env set AZURE_AI_MODEL_VERSION <model-version>
```

For `gpt-5.4` in East US 2:

```bash
azd env set MODEL_DEPLOYMENT_NAME gpt-5.4
azd env set AZURE_AI_MODEL_NAME gpt-5.4
azd env set AZURE_AI_MODEL_VERSION 2026-03-05
```

If deployment fails in another subscription or region, query the catalog with:

```bash
az cognitiveservices model list \
   --location eastus2 \
   --query "[?model.name=='gpt-5.4']"
```

### Foundry Skills SDK Notes

The Foundry Skills APIs used by this demo are preview APIs. Reference:
[Use skills with Microsoft Foundry agents (preview)](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?pivots=python)

The code creates the project client with preview APIs enabled:

```python
AIProjectClient(..., allow_preview=True)
```

The demo expects `azure-ai-projects` 2.2.0 or later, including these preview APIs:

- `project.beta.skills.create`
- `project.beta.skills.get`
- `project.beta.skills.list`
- `project.beta.skills.download`
- `project.beta.skills.create_from_files`
- `project.beta.toolboxes.create_version`
- `project.beta.toolboxes.update`

Publishing uses inline skill content with `SkillInlineContent`; the normal runner
downloads the active Foundry skill package into
`skills/<skill-name>/<default-version>/SKILL.md`.

The toolbox script includes a compatibility shim for older preview SDK builds
that expose `SkillReferenceParam` instead of the documented
`ToolboxSkillReference`, but the toolbox APIs are still preview and may require
upgrading `azure-ai-projects` if your installed package does not expose
`project.beta.toolboxes`.
