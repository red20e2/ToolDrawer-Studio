$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$ExePath = Join-Path $Root "dist\ToolDrawer Studio\ToolDrawer Studio.exe"
$OutputDir = Join-Path $Root "build\frozen-self-test"
if (-not (Test-Path $ExePath -PathType Leaf)) { throw "Packaged executable is missing: $ExePath" }
if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }

$env:QT_QPA_PLATFORM = "offscreen"
$SelfTestFlag = "--self-" + "test"
& $ExePath $SelfTestFlag "--output-dir" $OutputDir
if ($LASTEXITCODE -ne 0) { throw "Frozen verification failed with exit code $LASTEXITCODE" }

foreach ($Mode in @("foam", "gridfinity")) {
    $ModeDir = Join-Path $OutputDir $Mode
    foreach ($Extension in @("*.step", "*.stl", "*.dxf")) {
        $Files = @(Get-ChildItem -Path $ModeDir -Filter $Extension -File -ErrorAction SilentlyContinue)
        if ($Files.Count -lt 1) { throw "Frozen verification did not produce $Extension for $Mode" }
        foreach ($File in $Files) {
            if ($File.Length -le 0) { throw "Frozen verification produced an empty file: $($File.FullName)" }
        }
    }
}

Write-Host "frozen-self-test-ok"
