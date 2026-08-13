$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$WorkDir = Join-Path $Root "build\pyinstaller"
$DistDir = Join-Path $Root "dist"
$AppDir = Join-Path $DistDir "ToolDrawer Studio"
$ExePath = Join-Path $AppDir "ToolDrawer Studio.exe"
$SpecReference = Join-Path $Root "packaging\ToolDrawerStudio.spec"
$EntryPoint = Join-Path $Root "src\tooldrawer_studio\__main__.py"

if (-not (Test-Path $SpecReference -PathType Leaf)) { throw "PyInstaller spec is missing: $SpecReference" }
if (Test-Path $WorkDir) { Remove-Item $WorkDir -Recurse -Force }
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "ToolDrawer Studio" `
    --paths (Join-Path $Root "src") `
    --collect-all casadi `
    --workpath $WorkDir `
    --distpath $DistDir `
    $EntryPoint

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE" }
if (-not (Test-Path $ExePath -PathType Leaf)) { throw "Packaged executable was not created: $ExePath" }

Write-Host "packaged-exe=$ExePath"
