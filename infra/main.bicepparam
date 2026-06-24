using './main.bicep'

// All resources are provisioned in eastus2 for this demo.
param location = readEnvironmentVariable('AZURE_LOCATION', 'eastus2')

// Account names must be globally unique. Format: aif-<env name>-<random 4 chars>.
param accountName = 'aif-${toLower(readEnvironmentVariable('AZURE_ENV_NAME', 'demo'))}-${substring(uniqueString(readEnvironmentVariable('AZURE_SUBSCRIPTION_ID', 'local'), readEnvironmentVariable('AZURE_ENV_NAME', 'demo')), 0, 4)}'

// Foundry project + prompt-agent model.
param projectName = readEnvironmentVariable('AZURE_AI_PROJECT_NAME', 'aif-proj')
param projectDisplayName = 'Log Root Cause Analyzer'
param modelDeploymentName = readEnvironmentVariable('MODEL_DEPLOYMENT_NAME', 'gpt-5.4')
param modelName = readEnvironmentVariable('AZURE_AI_MODEL_NAME', 'gpt-5.4')
// gpt-5.4 version available in eastus2 from the Azure model catalog.
param modelVersion = readEnvironmentVariable('AZURE_AI_MODEL_VERSION', '2026-03-05')

// Deployment sizing.
param deploymentSkuName = readEnvironmentVariable('AZURE_AI_DEPLOYMENT_SKU', 'GlobalStandard')
param deploymentCapacity = int(readEnvironmentVariable('AZURE_AI_DEPLOYMENT_CAPACITY', '50'))

// Optional toolbox/MCP flow.
param foundryToolboxName = readEnvironmentVariable('FOUNDRY_TOOLBOX_NAME', 'logs-analysis-toolbox')

param tags = {
  workload: 'logs-analysis'
  environment: 'demo'
}
