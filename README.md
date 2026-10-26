# Red Vial 4 · GeoServer + visor web

Publica capas de la File Geodatabase de ArcGIS Pro sin PostgreSQL/PostGIS:

```
red_vial_4.gdb ──(sincronizar)──┬──> datos/red_vial_4.gpkg ──> GeoServer (localhost:8080) ──> ArcGIS Pro (WMS/WFS)
   (edición en ArcGIS Pro)      └──> docs/data/*.geojson ──(git push)──> GitHub Pages (visor web público)
```

Capas publicadas (`config.json`): `II_Predios/BG_Afectaciones_1` y todo `III_Interferencias`.

## Uso diario

| Archivo | Qué hace |
|---|---|
| `iniciar_geoserver.bat` | Inicia GeoServer (dejar la ventana abierta). Admin: http://localhost:8080/geoserver |
| `detener_geoserver.bat` | Apaga GeoServer |
| `sincronizar.bat` | Copia las capas editadas a GeoServer y al visor web (y hace `git push`). `sincronizar.bat --forzar` reescribe todo |
| `programar_sincronizacion.bat` | Crea una tarea de Windows que sincroniza cada 5 min en segundo plano |

Las ediciones deben estar **guardadas** en ArcGIS Pro (Guardar ediciones) para que la sincronización las vea.
Solo se reescriben las capas que cambiaron; las capas nuevas o que pasan de 0 a tener datos se publican solas.
Registro: `datos/sync.log`.

## Conectar desde ArcGIS Pro

Insertar → Conexiones → Servidor → **Nuevo servidor WMS** (o WFS):

- WMS: `http://localhost:8080/geoserver/red_vial_4/wms`
- WFS: `http://localhost:8080/geoserver/red_vial_4/wfs`

## Estructura

```
GEOSERVER/
├─ config.json              capas a publicar, rutas, workspace
├─ config.local.json        (opcional, no se sube) {"usuario": "admin", "clave": "..."} de GeoServer
├─ scripts/                 sync_gdb.py, publicar_geoserver.py, comun.py
├─ docs/                    visor web (GitHub Pages): index.html + data/*.geojson
├─ runtime/                 Java 21 + GeoServer 3.0.2 portables (no se suben)
├─ data_dir/                configuración de GeoServer (no se sube)
└─ datos/                   GeoPackage, estado y log (no se sube)
```

## Reinstalar en otra PC

1. Descargar en `runtime/`: Java 21 (Temurin JRE zip) en `runtime/java` y GeoServer *Platform Independent Binary* en `runtime/geoserver`.
2. `iniciar_geoserver.bat`, luego `sincronizar.bat --forzar`.
