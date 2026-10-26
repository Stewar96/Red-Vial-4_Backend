@echo off
rem Copia a GeoServer y al visor web las capas editadas en la GDB. Opciones: --forzar
set "PY=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
"%PY%" "%~dp0scripts\sync_gdb.py" --git %*
if "%1"=="" pause
