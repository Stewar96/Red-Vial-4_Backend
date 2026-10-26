@echo off
rem Inicia GeoServer portable (Java y GeoServer dentro de runtime\, configuracion en data_dir\)
set "RAIZ=%~dp0"
set "JAVA=%RAIZ%runtime\java\bin\java.exe"
set "GEOSERVER_HOME=%RAIZ%runtime\geoserver"
set "GEOSERVER_DATA_DIR=%RAIZ%data_dir"
if not exist "%GEOSERVER_DATA_DIR%" mkdir "%GEOSERVER_DATA_DIR%"

for /f "delims=" %%i in ('dir /b/s "%GEOSERVER_HOME%\webapps\geoserver\WEB-INF\lib\marlin*.jar"') do set "MARLIN_JAR=%%i"

echo GeoServer: http://localhost:8080/geoserver
echo Para apagarlo cierre esta ventana o ejecute detener_geoserver.bat
cd /d "%GEOSERVER_HOME%"
"%JAVA%" -Xms512m -Xmx2g --patch-module java.desktop="%MARLIN_JAR%" ^
  --add-exports=java.desktop/sun.awt.image=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED ^
  --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.lang.reflect=ALL-UNNAMED ^
  --add-opens=java.base/java.text=ALL-UNNAMED --add-opens=java.desktop/java.awt.font=ALL-UNNAMED ^
  --add-opens=java.desktop/sun.awt.image=ALL-UNNAMED --add-opens=java.naming/com.sun.jndi.ldap=ALL-UNNAMED ^
  --add-opens=java.desktop/sun.java2d.pipe=ALL-UNNAMED ^
  -DGEOSERVER_DATA_DIR="%GEOSERVER_DATA_DIR%" -Djava.awt.headless=true ^
  -DSTOP.PORT=8079 -DSTOP.KEY=geoserver -jar start.jar
