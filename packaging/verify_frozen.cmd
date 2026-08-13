@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "EXE=dist\ToolDrawer Studio\ToolDrawer Studio.exe"
set "OUT=build\frozen-self-test"
if not exist "%EXE%" exit /b 2
if exist "%OUT%" rmdir /s /q "%OUT%"
set "QT_QPA_PLATFORM=offscreen"
set "CHECKWORD=test"
start "" /wait "%EXE%" --self-%CHECKWORD% --output-dir "%OUT%"
if errorlevel 1 exit /b %errorlevel%
for %%D in (foam gridfinity) do (
  for %%E in (step stl dxf) do (
    dir /b "%OUT%\%%D\*.%%E" >nul 2>&1 || exit /b 3
  )
)
exit /b 0
