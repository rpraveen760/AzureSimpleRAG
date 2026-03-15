param(
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "",
    [string]$Location = "",
    [string]$ContainerEnv = "",
    [string]$ContainerApp = "",
    [string]$AcrName = "",
    [string]$ImageName = "",
    [string]$ImageTag = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    foreach ($rawLine in Get-Content $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path ("Env:{0}" -f $key) -Value $value
    }
}

function Require-Setting {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required environment setting: $Name"
    }
    return $value
}

function Test-AzCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    $previousPreference = $ErrorActionPreference
    try {
        $global:ErrorActionPreference = "Continue"
        & $Command *> $null
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $global:ErrorActionPreference = $previousPreference
    }
}

function Invoke-AzChecked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    $output = & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
    return $output
}

if ($EnvFile) {
    Import-DotEnv -Path $EnvFile
}

if (-not $SubscriptionId) {
    $SubscriptionId = $env:AZURE_SUBSCRIPTION_ID
}
if (-not $ResourceGroup) {
    $ResourceGroup = if ($env:RESOURCE_GROUP) { $env:RESOURCE_GROUP } else { "rg-docbrain" }
}
if (-not $Location) {
    $Location = if ($env:LOCATION) { $env:LOCATION } else { "eastus2" }
}
if (-not $ContainerEnv) {
    $ContainerEnv = if ($env:CONTAINER_ENV) { $env:CONTAINER_ENV } else { "docbrain-env" }
}
if (-not $ContainerApp) {
    $ContainerApp = if ($env:CONTAINER_APP) { $env:CONTAINER_APP } else { "docbrain-app" }
}
if (-not $AcrName) {
    $AcrName = if ($env:ACR_NAME) { $env:ACR_NAME } else { "docbrainacr" }
}
if (-not $ImageName) {
    $ImageName = if ($env:IMAGE_NAME) { $env:IMAGE_NAME } else { "docbrain" }
}
if (-not $ImageTag) {
    $ImageTag = if ($env:IMAGE_TAG) { $env:IMAGE_TAG } else { "latest" }
}

if (-not $SubscriptionId) {
    throw "SubscriptionId is required."
}

$openAiEndpoint = Require-Setting -Name "AZURE_OPENAI_ENDPOINT"
$openAiKey = Require-Setting -Name "AZURE_OPENAI_KEY"
$projectEndpoint = Require-Setting -Name "AZURE_AI_PROJECT_ENDPOINT"
$chatModel = Require-Setting -Name "AZURE_AI_CHAT_MODEL"
$embeddingModel = Require-Setting -Name "AZURE_AI_EMBEDDING_MODEL"
$searchEndpoint = Require-Setting -Name "AZURE_SEARCH_ENDPOINT"
$searchKey = Require-Setting -Name "AZURE_SEARCH_KEY"
$searchIndex = Require-Setting -Name "AZURE_SEARCH_INDEX"
$storageConnectionString = Require-Setting -Name "AZURE_STORAGE_CONNECTION_STRING"
$storageContainer = Require-Setting -Name "AZURE_STORAGE_CONTAINER"

$openAiApiVersion = if ($env:AZURE_OPENAI_API_VERSION) { $env:AZURE_OPENAI_API_VERSION } else { "2024-10-21" }
$appEnv = if ($env:APP_ENV) { $env:APP_ENV } else { "production" }
$siteName = if ($env:SITE_NAME) { $env:SITE_NAME } else { "DocBrain" }

az account set --subscription $SubscriptionId | Out-Null
az extension add --name containerapp --upgrade --only-show-errors | Out-Null

$loginServer = (az acr show --name $AcrName --query loginServer --output tsv --only-show-errors).Trim()
$acrUser = (az acr credential show --name $AcrName --query username --output tsv --only-show-errors).Trim()
$acrPass = (az acr credential show --name $AcrName --query "passwords[0].value" --output tsv --only-show-errors).Trim()
$imageRef = "{0}/{1}:{2}" -f $loginServer, $ImageName, $ImageTag

$envExists = Test-AzCommand {
    az containerapp env show --name $ContainerEnv --resource-group $ResourceGroup --only-show-errors
}
if (-not $envExists) {
    Write-Host "Creating Container Apps environment $ContainerEnv in $Location..."
    Invoke-AzChecked -FailureMessage "Failed to create Container Apps environment $ContainerEnv." -Command {
        az containerapp env create `
            --name $ContainerEnv `
            --resource-group $ResourceGroup `
            --location $Location `
            --only-show-errors
    } | Out-Null
}

$secretArgs = @(
    "openaikey=$openAiKey",
    "searchkey=$searchKey",
    "storageconn=$storageConnectionString",
    "acrpass=$acrPass"
)

$envArgs = @(
    "AZURE_AI_PROJECT_ENDPOINT=$projectEndpoint",
    "AZURE_OPENAI_ENDPOINT=$openAiEndpoint",
    "AZURE_OPENAI_KEY=secretref:openaikey",
    "AZURE_OPENAI_API_VERSION=$openAiApiVersion",
    "AZURE_AI_CHAT_MODEL=$chatModel",
    "AZURE_AI_EMBEDDING_MODEL=$embeddingModel",
    "AZURE_SEARCH_ENDPOINT=$searchEndpoint",
    "AZURE_SEARCH_KEY=secretref:searchkey",
    "AZURE_SEARCH_INDEX=$searchIndex",
    "AZURE_STORAGE_CONNECTION_STRING=secretref:storageconn",
    "AZURE_STORAGE_CONTAINER=$storageContainer",
    "APP_ENV=$appEnv",
    "SITE_NAME=$siteName",
    "SQLITE_DB_PATH=/app/data/docbrain.db",
    "PORT=8000"
)

$appExists = Test-AzCommand {
    az containerapp show --name $ContainerApp --resource-group $ResourceGroup --only-show-errors
}
if ($appExists) {
    Write-Host "Updating Container App $ContainerApp..."
    Invoke-AzChecked -FailureMessage "Failed to update Container App secrets." -Command {
        az containerapp secret set `
            --name $ContainerApp `
            --resource-group $ResourceGroup `
            --secrets @secretArgs `
            --only-show-errors
    } | Out-Null

    Invoke-AzChecked -FailureMessage "Failed to configure Container App registry access." -Command {
        az containerapp registry set `
            --name $ContainerApp `
            --resource-group $ResourceGroup `
            --server $loginServer `
            --username $acrUser `
            --password $acrPass `
            --only-show-errors
    } | Out-Null

    Invoke-AzChecked -FailureMessage "Failed to update Container App image or environment variables." -Command {
        az containerapp update `
            --name $ContainerApp `
            --resource-group $ResourceGroup `
            --image $imageRef `
            --replace-env-vars @envArgs `
            --only-show-errors
    } | Out-Null
}
else {
    Write-Host "Creating Container App $ContainerApp..."
    Invoke-AzChecked -FailureMessage "Failed to create Container App $ContainerApp." -Command {
        az containerapp create `
            --name $ContainerApp `
            --resource-group $ResourceGroup `
            --environment $ContainerEnv `
            --image $imageRef `
            --ingress external `
            --target-port 8000 `
            --cpu 0.5 `
            --memory 1.0Gi `
            --registry-server $loginServer `
            --registry-username $acrUser `
            --registry-password $acrPass `
            --secrets @secretArgs `
            --env-vars @envArgs `
            --only-show-errors
    } | Out-Null
}

$fqdnOutput = Invoke-AzChecked -FailureMessage "Failed to fetch the Container App URL." -Command {
    az containerapp show `
        --name $ContainerApp `
        --resource-group $ResourceGroup `
        --query properties.configuration.ingress.fqdn `
        --output tsv `
        --only-show-errors
}
$fqdn = ($fqdnOutput | Out-String).Trim()
if (-not $fqdn) {
    throw "Container App URL was empty after deployment."
}

Write-Host ""
Write-Host "Container App deployed."
Write-Host ("URL: https://{0}" -f $fqdn)
