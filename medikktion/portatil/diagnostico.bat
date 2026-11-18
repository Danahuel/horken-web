@echo off
chcp 65001 >nul
title Medikktion - Diagnostico
cd /d "%~dp0"
:menu
cls
echo ================================================
echo   MEDIKKTION - Diagnostico de maquinaria
echo ================================================
echo   1. Leer MAQUINA (lector RP1210 conectado)
echo   2. Leer COCHE / furgoneta (ELM327)
echo   3. Prueba con maquina simulada
echo   4. Ver lectores instalados
echo   5. Comprobar que todo funciona
echo   6. Configurar (primera vez)
echo   7. Reproducir una grabacion
echo   8. Salir
echo ================================================
set /p op=Elige una opcion:
if "%op%"=="1" goto leer
if "%op%"=="2" goto coche
if "%op%"=="3" goto demo
if "%op%"=="4" goto lectores
if "%op%"=="5" goto comprobar
if "%op%"=="6" goto configurar
if "%op%"=="7" goto reproducir
if "%op%"=="8" exit /b
goto menu

:lectores
py -m medikktion adaptadores
pause
goto menu

:demo
echo Maquinas simuladas: cat320  fuchs  arjes  hamm
set /p esc=Cual [fuchs]: 
if "%esc%"=="" set esc=fuchs
py -m medikktion demo --escenario %esc% --segundos 120
pause
goto menu

:reproducir
echo Grabaciones disponibles:
dir /b /o-d sesiones\grabaciones\*.blf 2>nul
echo.
set /p arch=Nombre del archivo (o arrastralo aqui): 
if "%arch%"=="" goto menu
set arch=%arch:"=%
if not exist "%arch%" set arch=sesiones\grabaciones\%arch%
set /p vel=Velocidad (1 = tiempo real, 5 = cinco veces mas rapido) [1]: 
if "%vel%"=="" set vel=1
py -m medikktion reproducir "%arch%" --velocidad %vel%
pause
goto menu

:comprobar
py -m medikktion comprobar
pause
goto menu

:configurar
py -m medikktion configurar
pause
goto menu

:coche
set /p puerto=Puerto del ELM327 (ej. COM5, vacio = buscar): 
set /p km=Km que marca el cuadro (para detectar manipulacion, vacio = no): 
set extra=
if not "%puerto%"=="" set extra=--puerto %puerto%
if not "%km%"=="" set extra=%extra% --km-cuadro %km%
py -m medikktion coche %extra%
pause
goto menu

:leer
py -m medikktion adaptadores
echo.
set /p canal=Nombre del lector (lo que va despues de --canal, ej. NULN2R32):
set /p disp=Numero de dispositivo [1]:
if "%disp%"=="" set disp=1
echo Tipos: excavadora_20t excavadora_grande manipuladora cargadora_ruedas dumper_articulado bulldozer rodillo trituradora retro_mixta minicargadora camion
set /p clase=Tipo de maquina:
if "%clase%"=="" set clase=generica
set /p ubic=Ubicacion (ej. Munich):
set grab=
set g=
set /p g=Grabar todas las tramas para diagnostico? (s/N): 
if /i "%g%"=="s" set grab=--grabar
echo.
echo Leyendo... los datos aparecen en el movil. Pulsa Ctrl+C para terminar y generar el informe (si pregunta "Terminar el trabajo por lotes", responde N).
py -m medikktion leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --bitrate 0 --j1587 %grab% --clase %clase% --ubicacion "%ubic%"
if errorlevel 1 (
  echo.
  echo Probando en modo J1939...
  py -m medikktion leer --interfaz rp1210 --canal %canal% --dispositivo %disp% --protocolo J1939 --bitrate 0 %grab% --clase %clase% --ubicacion "%ubic%"
)
pause
goto menu
