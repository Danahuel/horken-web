@echo off
chcp 65001 >nul
title Horken - Diagnostico
cd /d "%~dp0"
:menu
cls
echo ================================================
echo   HORKEN - Diagnostico de maquinaria
echo ================================================
echo   1. Leer maquina (lector conectado)
echo   2. Prueba con maquina simulada (Caterpillar)
echo   3. Ver lectores instalados
echo   4. Salir
echo ================================================
set /p op=Elige una opcion:
if "%op%"=="1" goto leer
if "%op%"=="2" goto demo
if "%op%"=="3" goto lectores
if "%op%"=="4" exit /b
goto menu

:lectores
py -m horken_diag adaptadores
pause
goto menu

:demo
py -m horken_diag demo --escenario cat320 --segundos 60
pause
goto menu

:leer
py -m horken_diag adaptadores
echo.
set /p canal=Nombre del lector (lo que va despues de --canal, ej. NULN2R32):
set /p disp=Numero de dispositivo [1]:
if "%disp%"=="" set disp=1
echo Tipos: excavadora_20t excavadora_grande cargadora_ruedas dumper_articulado bulldozer rodillo trituradora retro_mixta minicargadora camion
set /p clase=Tipo de maquina:
if "%clase%"=="" set clase=generica
set /p ubic=Ubicacion (ej. Munich):
echo.
echo Leyendo... los datos aparecen en el movil. Pulsa Ctrl+C para terminar y generar el informe (si pregunta "Terminar el trabajo por lotes", responde N).
py -m horken_diag leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --bitrate 0 --clase %clase% --ubicacion "%ubic%"
if errorlevel 1 (
  echo.
  echo Probando en modo J1939...
  py -m horken_diag leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --protocolo J1939 --bitrate 0 --clase %clase% --ubicacion "%ubic%"
)
pause
goto menu
