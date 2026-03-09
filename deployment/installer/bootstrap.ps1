Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Mode = if ($env:LAWCOPILOT_DEPLOYMENT_MODE) { $env:LAWCOPILOT_DEPLOYMENT_MODE } else { "local-first-hybrid" }

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "[LawCopilot] ERROR: Python is required for the pilot bootstrap flow."
}

$env:LAWCOPILOT_DEPLOYMENT_MODE = $Mode
python (Join-Path $Root "scripts\pilot_local.ps1") -DeploymentMode $Mode
