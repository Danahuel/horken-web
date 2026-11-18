@echo off
rem Abre la estacion de lectura de Medikktion (sin ventana negra).
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -m medikktion estacion
) else (
  start "" pythonw -m medikktion estacion
)
