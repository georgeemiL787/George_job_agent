param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build
}
# Always clear dist so stale PyInstaller folders (e.g. old spec names) are not left behind.
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

# Install Playwright browser locally so PyInstaller bundles it automatically
$env:PLAYWRIGHT_BROWSERS_PATH="0"
& .\.venv\Scripts\python.exe -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    throw "Playwright browser installation failed."
}

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\george_job_agent.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$ExePath = Join-Path $Root "dist\GeorgeJobAgent\GeorgeJobAgent.exe"
if (-not (Test-Path $ExePath)) {
    throw "Expected desktop executable was not created: $ExePath"
}

# Copy .env file so the user doesn't have to setup API keys again
$EnvSource = Join-Path $Root ".env"
$EnvDest = Join-Path $Root "dist\GeorgeJobAgent\.env"
if (Test-Path $EnvSource) {
    Copy-Item $EnvSource $EnvDest -Force
    Write-Host "Copied .env to dist directory."
}

Write-Host "Desktop build written to $ExePath"
