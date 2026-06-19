#!/usr/bin/env bash
# Provision the Microsoft Foundry infrastructure for the log root-cause prompt agent.
#
# What this does:
#   1. Creates a resource group in eastus2.
#   2. Deploys infra/main.bicep (AI Services account + project + GPT deployment).
#   3. Prints the project endpoint and explains how to create/invoke the prompt agent.
#
# Re-running is safe: `az group create` and `az deployment group create` are
# idempotent for the same inputs (ARM does an incremental deployment).
#
# Prerequisites:
#   - Azure CLI (`az version`) and an authenticated session (`az login`).
#   - Contributor/Owner (or Azure AI Owner) on the target subscription.
#   - Microsoft.CognitiveServices provider registered (see step 0).
#
# Auth note: NO keys are used. Local auth is disabled on the account; the
# prompt agent is invoked with Entra ID (DefaultAzureCredential). Make sure your
# identity has the "Foundry User" (or higher) role on the project.

set -euo pipefail

# ----------------------------------------------------------------------------
# Configuration (override via environment variables if desired).
# ----------------------------------------------------------------------------
LOCATION="${AZURE_REGION:-eastus2}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-foundry-logs-analysis}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-foundry-logs-analysis}"
MODEL_DEPLOYMENT_NAME="${MODEL_DEPLOYMENT_NAME:-gpt-5.1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP_FILE="${SCRIPT_DIR}/main.bicep"
BICEP_PARAMS="${SCRIPT_DIR}/main.bicepparam"

echo "==> Region:          ${LOCATION}"
echo "==> Resource group:  ${RESOURCE_GROUP}"
echo "==> Model deployment: ${MODEL_DEPLOYMENT_NAME}"

# ----------------------------------------------------------------------------
# Step 0: Ensure the Cognitive Services provider is registered (one-time).
# ----------------------------------------------------------------------------
echo "==> Ensuring Microsoft.CognitiveServices provider is registered..."
az provider register --namespace Microsoft.CognitiveServices --wait

# ----------------------------------------------------------------------------
# Step 1: Create the resource group in eastus2.
# ----------------------------------------------------------------------------
echo "==> Creating resource group ${RESOURCE_GROUP} in ${LOCATION}..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

# ----------------------------------------------------------------------------
# Step 2: Deploy the Bicep template (account + project + GPT deployment).
# ----------------------------------------------------------------------------
echo "==> Deploying Bicep template..."
az deployment group create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${DEPLOYMENT_NAME}" \
  --template-file "${BICEP_FILE}" \
  --parameters "${BICEP_PARAMS}" \
  --output none

# ----------------------------------------------------------------------------
# Step 3: Read deployment outputs.
# ----------------------------------------------------------------------------
PROJECT_ENDPOINT="$(az deployment group show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${DEPLOYMENT_NAME}" \
  --query "properties.outputs.projectEndpoint.value" \
  --output tsv)"

PROJECT_NAME="$(az deployment group show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${DEPLOYMENT_NAME}" \
  --query "properties.outputs.projectName.value" \
  --output tsv)"

echo ""
echo "============================================================"
echo " Provisioning complete."
echo "============================================================"
echo " Foundry project:    ${PROJECT_NAME}"
echo " Project endpoint:   ${PROJECT_ENDPOINT}"
echo " Model deployment:   ${MODEL_DEPLOYMENT_NAME}"
echo ""
echo " Next steps:"
echo "   1. Copy .env.example to .env and set:"
echo "        FOUNDRY_PROJECT_ENDPOINT=${PROJECT_ENDPOINT}"
echo "        MODEL_DEPLOYMENT_NAME=${MODEL_DEPLOYMENT_NAME}"
echo "        AZURE_REGION=${LOCATION}"
echo ""
echo "   2. Grant your identity the 'Foundry User' role on the project"
echo "      (required because local/key auth is disabled):"
echo "        az role assignment create \\"
echo "          --assignee \"\$(az ad signed-in-user show --query id -o tsv)\" \\"
echo "          --role \"Foundry User\" \\"
echo "          --scope \"\$(az cognitiveservices account show -g ${RESOURCE_GROUP} -n <accountName> --query id -o tsv)\""
echo ""
echo "   3. Publish the Foundry Skills, then invoke the prompt agent:"
echo "        pip install -r requirements.txt"
echo "        python -m src.skills.publish_skill"
echo "        python -m src.agent.run_agent --log sample_logs/web.log"
echo ""
echo "   The prompt agent is backed by the configured GPT deployment whose system"
echo "   instructions come from the selected active skill downloaded under skills/."
echo "============================================================"
