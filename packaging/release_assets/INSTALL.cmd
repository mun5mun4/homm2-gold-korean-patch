@echo off
cd /d "%~dp0"
"%~dp0homm2-ko-patcher.exe" preflight %*
if errorlevel 1 goto end
"%~dp0homm2-ko-patcher.exe" install %*
:end
pause
