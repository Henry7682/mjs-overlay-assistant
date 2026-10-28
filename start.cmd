@echo off
cd /d "%~dp0"
if exist "dist\MjsOverlay-0.3.10-preview\MjsOverlay-0.3.10-preview.exe" (
  start "" "dist\MjsOverlay-0.3.10-preview\MjsOverlay-0.3.10-preview.exe"
) else if exist "dist\MjsOverlay-0.3.8-preview\MjsOverlay-0.3.8-preview.exe" (
  start "" "dist\MjsOverlay-0.3.8-preview\MjsOverlay-0.3.8-preview.exe"
) else if exist "dist\MjsOverlay-0.3.1-preview\MjsOverlay-0.3.1-preview.exe" (
  start "" "dist\MjsOverlay-0.3.1-preview\MjsOverlay-0.3.1-preview.exe"
) else if exist "dist\MjsOverlay-0.3.0-preview\MjsOverlay-0.3.0-preview.exe" (
  start "" "dist\MjsOverlay-0.3.0-preview\MjsOverlay-0.3.0-preview.exe"
) else if exist "dist\MjsOverlay-0.2.6-preview\MjsOverlay-0.2.6-preview.exe" (
  start "" "dist\MjsOverlay-0.2.6-preview\MjsOverlay-0.2.6-preview.exe"
) else if exist "dist\MjsOverlay-0.2.5-preview\MjsOverlay-0.2.5-preview.exe" (
  start "" "dist\MjsOverlay-0.2.5-preview\MjsOverlay-0.2.5-preview.exe"
) else if exist "dist\MjsOverlay-0.2.4-preview\MjsOverlay-0.2.4-preview.exe" (
  start "" "dist\MjsOverlay-0.2.4-preview\MjsOverlay-0.2.4-preview.exe"
) else if exist "dist\MjsOverlay-0.2.3-preview\MjsOverlay-0.2.3-preview.exe" (
  start "" "dist\MjsOverlay-0.2.3-preview\MjsOverlay-0.2.3-preview.exe"
) else if exist "dist\MjsOverlay-0.2.2-preview\MjsOverlay-0.2.2-preview.exe" (
  start "" "dist\MjsOverlay-0.2.2-preview\MjsOverlay-0.2.2-preview.exe"
) else if exist "dist\MjsOverlay-0.2.1-preview\MjsOverlay-0.2.1-preview.exe" (
  start "" "dist\MjsOverlay-0.2.1-preview\MjsOverlay-0.2.1-preview.exe"
) else if exist "dist\MjsOverlay-0.2-preview\MjsOverlay-0.2-preview.exe" (
  start "" "dist\MjsOverlay-0.2-preview\MjsOverlay-0.2-preview.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "main.py"
) else if exist "dist\MjsOverlay\MjsOverlay.exe" (
  start "" "dist\MjsOverlay\MjsOverlay.exe"
) else (
  echo Please use the portable package, or create .venv with Python 3.11 and requirements.lock.txt.
  pause
)
