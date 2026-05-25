param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\george_job_agent.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$ExePath = Join-Path $Root "dist\GeorgeJobAgent\GeorgeJobAgent.exe"
if (-not (Test-Path $ExePath)) {
    throw "Expected desktop executable was not created: $ExePath"
}

Write-Host "Desktop build written to $ExePath"
