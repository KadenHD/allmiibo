param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath "./.venv-build/Scripts/python.exe")) {
    & $Python -m venv ./.venv-build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$buildPython = "./.venv-build/Scripts/python.exe"
& $buildPython -m pip install -r ./requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $buildPython -m PyInstaller --noconfirm --clean ./AllmiiboManager.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Executable created: ./dist/AllmiiboManager.exe"
