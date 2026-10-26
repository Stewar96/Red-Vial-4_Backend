@echo off
set "RAIZ=%~dp0"
cd /d "%RAIZ%runtime\geoserver"
"%RAIZ%runtime\java\bin\java.exe" -DSTOP.PORT=8079 -DSTOP.KEY=geoserver -jar start.jar --stop
