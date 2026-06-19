// Microsoft Foundry infrastructure for the log root-cause prompt-agent demo.
// Provisions an Azure AI Services (Foundry) account, a Foundry project, and a
// gpt-5.4 model deployment. eastus2 is the default demo region.

@description('Azure region for all resources. Defaults to eastus2 for this demo.')
param location string = 'eastus2'

@description('Name of the Azure AI Services (Foundry) account. Must be globally unique. azd uses aif-<env name>-<random 4 chars>.')
@minLength(2)
@maxLength(64)
param accountName string = 'aif-${uniqueString(resourceGroup().id)}'

@description('Name of the Foundry project that hosts the prompt agent.')
@minLength(2)
@maxLength(64)
param projectName string = 'aif-proj'

@description('Friendly display name for the Foundry project.')
param projectDisplayName string = 'Log Root Cause Analyzer'

@description('Name of the model deployment used by the prompt agent.')
param modelDeploymentName string = 'gpt-5.4'

@description('Catalog name of the model to deploy.')
param modelName string = 'gpt-5.4'

@description('Specific model version. gpt-5.4 is available in eastus2 as 2026-03-05.')
param modelVersion string = '2026-03-05'

@description('Deployment SKU (e.g. GlobalStandard, Standard).')
param deploymentSkuName string = 'GlobalStandard'

@description('Provisioned throughput / capacity (in thousands of TPM) for the deployment.')
@minValue(1)
param deploymentCapacity int = 10

@description('Tags applied to all resources.')
param tags object = {
  workload: 'logs-analysis'
  environment: 'demo'
}

// Azure AI Services multi-service account that backs the Foundry project.
resource account 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    // Required so the account can host Foundry projects.
    allowProjectManagement: true
    // customSubDomainName is required for token-based (Entra ID) auth.
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    // Prefer managed identity / Entra ID auth over account keys.
    disableLocalAuth: true
  }
}

// Foundry project that the prompt agent lives in.
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-10-01-preview' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  tags: tags
  properties: {
    displayName: projectDisplayName
    description: 'Project hosting the log root-cause analysis prompt agent.'
  }
}

// GPT model deployment consumed by the prompt agent.
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: modelDeploymentName
  sku: {
    name: deploymentSkuName
    capacity: deploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: empty(modelVersion) ? null : modelVersion
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

@description('Name of the Foundry account.')
output accountName string = account.name

@description('Name of the Foundry project.')
output projectName string = project.name

@description('Foundry project endpoint to use with the Azure AI Projects SDK.')
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'

@description('Foundry project endpoint exported for the Python demo.')
output FOUNDRY_PROJECT_ENDPOINT string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'

@description('Foundry project endpoint using the Azure AI Projects azd naming convention.')
output AZURE_AI_PROJECT_ENDPOINT string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'

@description('Azure region exported for local scripts.')
output AZURE_REGION string = location

@description('Account-level AI Services endpoint.')
output accountEndpoint string = account.properties.endpoint

@description('Name of the GPT model deployment.')
output modelDeploymentName string = modelDeployment.name

@description('Model deployment name exported for the Python demo.')
output MODEL_DEPLOYMENT_NAME string = modelDeployment.name

@description('Foundry skill name exported for the direct-download demo.')
output FOUNDRY_SKILL_NAME string = 'web-logs-analysis'

@description('Comma-separated Foundry skill names exported for the multi-skill direct-download demo.')
output FOUNDRY_SKILL_NAMES string = 'web-logs-analysis,k8s-logs-analysis'

@description('Local source skill path exported for the Python publishing demo.')
output SKILL_PATH string = 'source/skills/web-logs-analysis/SKILL.md'

@description('Local source skill path exported for the Python publishing demo.')
output SOURCE_SKILL_PATH string = 'source/skills/web-logs-analysis/SKILL.md'

@description('Comma-separated local source skill paths exported for the multi-skill Python publishing demo.')
output SKILL_PATHS string = 'source/skills/web-logs-analysis/SKILL.md,source/skills/k8s-logs-analysis/SKILL.md'

@description('Comma-separated local source skill paths exported for the multi-skill Python publishing demo.')
output SOURCE_SKILL_PATHS string = 'source/skills/web-logs-analysis/SKILL.md,source/skills/k8s-logs-analysis/SKILL.md'

@description('Prompt agent name exported for the Python demo.')
output AGENT_NAME string = 'logs-analysis-agent'

@description('Foundry account name exported for follow-up role assignments.')
output AZURE_AI_ACCOUNT_NAME string = account.name

@description('Foundry project name exported for tooling.')
output AZURE_AI_PROJECT_NAME string = project.name
