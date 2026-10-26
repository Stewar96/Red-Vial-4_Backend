@echo off
rem Crea una tarea de Windows que sincroniza cada 5 minutos en segundo plano (sin ventana).
rem Para quitarla:  schtasks /Delete /TN "RedVial4_Sincronizar" /F
set "PYW=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\pythonw.exe"
schtasks /Create /F /SC MINUTE /MO 5 /TN "RedVial4_Sincronizar" /TR "\"%PYW%\" \"%~dp0scripts\sync_gdb.py\" --git"
pause
