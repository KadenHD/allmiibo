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

Copy-Item -LiteralPath "./LICENSE" -Destination "./dist/LICENSE.txt" -Force
Copy-Item -LiteralPath "./THIRD_PARTY_NOTICES.md" -Destination "./dist/THIRD_PARTY_NOTICES.md" -Force
Copy-Item -LiteralPath "./DISCLAIMER.md" -Destination "./dist/DISCLAIMER.md" -Force

Write-Host "Executable created: ./dist/AllmiiboManager.exe"
