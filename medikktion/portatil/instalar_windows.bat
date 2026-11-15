@echo off
chcp 65001 >nul
title Medikktion - Instalacion
cd /d "%~dp0"
echo === Medikktion: instalando dependencias ===
py -c "import struct,sys; print('Python', sys.version.split()[0], struct.calcsize('P')*8, 'bits')"
if errorlevel 1 (
  echo.
  echo No se encuentra Python. Instalalo desde https://www.python.org/downloads/windows/
  echo y marca la casilla "Add python.exe to PATH".
  pause
  exit /b 1
)
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if not exist config.json copy config.ejemplo.json config.json >nul
echo.
echo === Lectores RP1210 instalados en este PC ===
py -m medikktion adaptadores
echo.
echo Listo. Abre "diagnostico.bat" para empezar.
pause
