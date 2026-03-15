param(
    [string]$SubscriptionId = "",
    [string]$AcrName = "",
    [string]$ImageName = "",
    [string]$ImageTag = "",
    [switch]$AlsoTagLatest
)

$ErrorActionPreference = "Stop"

if (-not $SubscriptionId) {
    $SubscriptionId = $env:AZURE_SUBSCRIPTION_ID
}
if (-not $AcrName) {
    $AcrName = $env:ACR_NAME
}
if (-not $ImageName) {
    $ImageName = $env:IMAGE_NAME
}
if (-not $ImageTag) {
    $ImageTag = $env:IMAGE_TAG
}
if (-not $ImageTag) {
    $ImageTag = "latest"
}

if (-not $AcrName) {
    throw "AcrName is required."
}
if (-not $ImageName) {
    throw "ImageName is required."
}

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId | Out-Null
}

$loginServer = (az acr show --name $AcrName --query loginServer --output tsv --only-show-errors).Trim()
if (-not $loginServer) {
    throw "Could not determine the ACR login server for '$AcrName'."
}

Write-Host "Logging in to ACR $AcrName..."
az acr login --name $AcrName --only-show-errors | Out-Null

$tags = @(
    ("{0}/{1}:{2}" -f $loginServer, $ImageName, $ImageTag)
)

if ($AlsoTagLatest.IsPresent -and $ImageTag -ne "latest") {
    $tags += ("{0}/{1}:latest" -f $loginServer, $ImageName)
}

$buildArgs = @("build")
foreach ($tag in $tags) {
    $buildArgs += @("-t", $tag)
}
$buildArgs += "."

Write-Host "Building Docker image..."
& docker @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed."
}

foreach ($tag in $tags) {
    Write-Host "Pushing $tag..."
    & docker push $tag
    if ($LASTEXITCODE -ne 0) {
        throw "Docker push failed for $tag."
    }
}

Write-Host "Image push complete:"
foreach ($tag in $tags) {
    Write-Host "  $tag"
}
