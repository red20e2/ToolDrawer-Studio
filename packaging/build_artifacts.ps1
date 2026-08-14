param(
    [string]$AppVersion = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($AppVersion)) {
    $AppVersion = (python -c "from tooldrawer_studio.version import __version__; print(__version__)").Trim()
}
if ([string]::IsNullOrWhiteSpace($AppVersion)) { throw "Application version is empty" }

$ArtifactsDir = Join-Path $Root "artifacts"
$AppDir = Join-Path $Root "dist\ToolDrawer Studio"
$SetupPath = Join-Path $ArtifactsDir "ToolDrawer-Studio-$AppVersion-Setup.exe"
$PortablePath = Join-Path $ArtifactsDir "ToolDrawer-Studio-$AppVersion-Portable.zip"
$HashesPath = Join-Path $ArtifactsDir "SHA256SUMS.txt"
$IssPath = Join-Path $Root "packaging\ToolDrawerStudio.iss"

if (Test-Path $ArtifactsDir) { Remove-Item $ArtifactsDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

& (Join-Path $Root "packaging\build_app.ps1")
if ($LASTEXITCODE -ne 0) { throw "Application build failed" }
& (Join-Path $Root "packaging\verify_frozen.ps1")
if ($LASTEXITCODE -ne 0) { throw "Frozen application verification failed" }

$Iscc = $null
$Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Command) { $Iscc = $Command.Source }
if (-not $Iscc) {
    $Candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $Iscc = $Candidates | Where-Object { $_ -and (Test-Path $_ -PathType Leaf) } | Select-Object -First 1
}
if (-not $Iscc) { throw "ISCC.exe was not found" }

& $Iscc "/DAppVersion=$AppVersion" $IssPath
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
if (-not (Test-Path $SetupPath -PathType Leaf)) { throw "Setup artifact was not created" }

if (Test-Path $PortablePath) { Remove-Item $PortablePath -Force }
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $PortablePath -CompressionLevel Optimal
if (-not (Test-Path $PortablePath -PathType Leaf)) { throw "Portable artifact was not created" }

python (Join-Path $Root "packaging\write_hashes.py") $HashesPath $SetupPath $PortablePath
if ($LASTEXITCODE -ne 0) { throw "Checksum generation failed" }

foreach ($Artifact in @($SetupPath, $PortablePath, $HashesPath)) {
    if (-not (Test-Path $Artifact -PathType Leaf)) { throw "Missing artifact: $Artifact" }
    if ((Get-Item $Artifact).Length -le 0) { throw "Empty artifact: $Artifact" }
}

Write-Host "setup=$SetupPath"
Write-Host "portable=$PortablePath"
Write-Host "hashes=$HashesPath"
