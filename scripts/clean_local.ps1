# Remove local build artifacts and caches (safe for git — these paths are gitignored).
param(
    [switch]$IncludeWorkspaceOutputs
)

$ErrorActionPreference = "SilentlyContinue"

foreach ($dir in @("build", "dist", ".pytest_cache", ".ruff_cache", ".mypy_cache")) {
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir
        Write-Host "Removed $dir"
    }
}

Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "Removed __pycache__ directories"

if ($IncludeWorkspaceOutputs) {
    foreach ($dir in @(
        "workspace/logs",
        "workspace/cv/tailored",
        "workspace/cover_letters",
        "workspace/packages"
    )) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            Write-Host "Cleared $dir"
        }
    }
}

Write-Host "Done."
