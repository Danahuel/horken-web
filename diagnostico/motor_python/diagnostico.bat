@echo off
chcp 65001 >nul
title Horken - Diagnostico
cd /d "%~dp0"
:menu
cls
echo ================================================
echo   HORKEN - Diagnostico de maquinaria
echo ================================================
echo   1. Leer MAQUINA (lector RP1210 conectado)
echo   2. Leer COCHE / furgoneta (ELM327)
echo   3. Prueba con maquina simulada
echo   4. Ver lectores instalados
echo   5. Comprobar que todo funciona
echo   6. Configurar (primera vez)
echo   7. Salir
echo ================================================
set /p op=Elige una opcion:
if "%op%"=="1" goto leer
if "%op%"=="2" goto coche
if "%op%"=="3" goto demo
if "%op%"=="4" goto lectores
if "%op%"=="5" goto comprobar
if "%op%"=="6" goto configurar
if "%op%"=="7" exit /b
goto menu

:lectores
py -m horken_diag adaptadores
pause
goto menu

:demo
echo Maquinas simuladas: cat320  fuchs  arjes  hamm
set /p esc=Cual [fuchs]: 
if "%esc%"=="" set esc=fuchs
py -m horken_diag demo --escenario %esc% --segundos 120
pause
goto menu

:comprobar
py -m horken_diag comprobar
pause
goto menu

:configurar
py -m horken_diag configurar
pause
goto menu

:coche
set /p puerto=Puerto del ELM327 (ej. COM5, vacio = buscar): 
set /p km=Km que marca el cuadro (para detectar manipulacion, vacio = no): 
set extra=
if not "%puerto%"=="" set extra=--puerto %puerto%
if not "%km%"=="" set extra=%extra% --km-cuadro %km%
py -m horken_diag coche %extra%
pause
goto menu

:leer
py -m horken_diag adaptadores
echo.
set /p canal=Nombre del lector (lo que va despues de --canal, ej. NULN2R32):
set /p disp=Numero de dispositivo [1]:
if "%disp%"=="" set disp=1
echo Tipos: excavadora_20t excavadora_grande manipuladora cargadora_ruedas dumper_articulado bulldozer rodillo trituradora retro_mixta minicargadora camion
set /p clase=Tipo de maquina:
if "%clase%"=="" set clase=generica
set /p ubic=Ubicacion (ej. Munich):
echo.
echo Leyendo... los datos aparecen en el movil. Pulsa Ctrl+C para terminar y generar el informe (si pregunta "Terminar el trabajo por lotes", responde N).
py -m horken_diag leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --bitrate 0 --j1587 --clase %clase% --ubicacion "%ubic%"
if errorlevel 1 (
  echo.
  echo Probando en modo J1939...
  py -m horken_diag leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --protocolo J1939 --bitrate 0 --clase %clase% --ubicacion "%ubic%"
)
pause
goto menu
