$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$WorkDir = Join-Path $Root "build\pyinstaller"
$DistDir = Join-Path $Root "dist"
$AppDir = Join-Path $DistDir "ToolDrawer Studio"
$ExePath = Join-Path $AppDir "ToolDrawer Studio.exe"
$SourceSpec = Join-Path $Root "packaging\ToolDrawerStudio.spec"
$StagedSpec = Join-Path $Root "ToolDrawerStudio.build.spec"

if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
if (Test-Path $StagedSpec) { Remove-Item $StagedSpec -Force }
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
Copy-Item $SourceSpec $StagedSpec -Force

try {
    python -m PyInstaller --noconfirm --clean --workpath $WorkDir --distpath $DistDir $StagedSpec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path $ExePath -PathType Leaf)) { throw "Packaged executable was not created: $ExePath" }
}
finally {
    if (Test-Path $StagedSpec) { Remove-Item $StagedSpec -Force }
}

Write-Host "packaged-exe=$ExePath"
