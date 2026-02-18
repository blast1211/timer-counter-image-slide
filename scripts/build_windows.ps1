param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$PSNativeCommandUseErrorActionPreference = $true

function Invoke-Step {
    param([string]$Command)
    Write-Host ">> $Command"
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $Command"
    }
}

if ($Clean) {
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

$sep = ";"

Invoke-Step "uv run python -m PyInstaller --noconfirm --clean --windowed --name slideshow-app --paths code --add-data `"src${sep}src`" code/app.py"
Invoke-Step "uv run python -m PyInstaller --noconfirm --clean --windowed --name subtitle-editor --paths code code/subtitle_editor.py"

Write-Host "Build finished. Outputs are in dist/slideshow-app and dist/subtitle-editor"
