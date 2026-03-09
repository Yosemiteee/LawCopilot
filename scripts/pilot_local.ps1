param(
  [string]$DeploymentMode = "local-first-hybrid"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeDir = Join-Path $Root "artifacts\runtime"
$EnvFile = Join-Path $RuntimeDir "pilot.env"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (-not (Test-Path $EnvFile)) {
  $jwt = [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
  $admin = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
  @"
LAWCOPILOT_JWT_SECRET=$jwt
LAWCOPILOT_BOOTSTRAP_ADMIN_KEY=$admin
LAWCOPILOT_OFFICE_ID=default-office
LAWCOPILOT_RELEASE_CHANNEL=pilot
LAWCOPILOT_ENVIRONMENT=pilot
LAWCOPILOT_CONNECTOR_DRY_RUN=true
"@ | Set-Content -Path $EnvFile -Encoding UTF8
}

$rows = @{}
Get-Content $EnvFile | ForEach-Object {
  if ($_ -match "=") {
    $key, $value = $_ -split "=", 2
    $rows[$key] = $value
  }
}
$rows["LAWCOPILOT_DEPLOYMENT_MODE"] = $DeploymentMode
($rows.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) | Set-Content -Path $EnvFile -Encoding UTF8

Write-Host "[LawCopilot] Pilot environment prepared: $EnvFile"
Write-Host "[LawCopilot] Next steps:"
Write-Host "  1. python -m venv apps\api\.venv"
Write-Host "  2. apps\api\.venv\Scripts\pip install -r apps\api\requirements.txt"
Write-Host "  3. cd apps\ui; npm install; npm run build"
Write-Host "  4. cd apps\desktop; npm install; npm test"
