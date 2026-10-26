"""Sincroniza capas de la GDB hacia GeoPackage (GeoServer) y GeoJSON (visor web).

Solo reescribe las capas cuyo contenido cambió desde la última ejecución.
Ejecutar con el Python de ArcGIS Pro (trae GDAL):

    python sync_gdb.py            # capas modificadas
    python sync_gdb.py --forzar   # todas las capas
    python sync_gdb.py --git      # además commit + push de docs/ si hubo cambios
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

from osgeo import gdal, ogr

import publicar_geoserver
from comun import RAIZ, cargar_config, color_capa, configurar_log, ruta, titulo_capa

gdal.UseExceptions()
log = configurar_log()

TIPOS = {
    ogr.wkbPoint: "punto", ogr.wkbMultiPoint: "punto",
    ogr.wkbLineString: "linea", ogr.wkbMultiLineString: "linea",
    ogr.wkbPolygon: "poligono", ogr.wkbMultiPolygon: "poligono",
}


def listar_capas(cfg, gdb):
    raiz = gdb.GetRootGroup()
    capas = []
    for item in cfg["capas"]:
        disponibles = raiz.OpenGroup(item["dataset"]).GetVectorLayerNames() or []
        nombres = disponibles if item["incluir"] == "*" else [n for n in item["incluir"] if n in disponibles]
        for faltante in set([] if item["incluir"] == "*" else item["incluir"]) - set(nombres):
            log.warning("Capa %s no existe en %s", faltante, item["dataset"])
        capas += [(item["grupo"], n) for n in nombres]
    return capas


def huella(capa):
    """Hash del esquema + geometrías + atributos; detecta cualquier edición."""
    h = hashlib.md5()
    defn = capa.GetLayerDefn()
    for i in range(defn.GetFieldCount()):
        fd = defn.GetFieldDefn(i)
        h.update(f"{fd.GetName()}:{fd.GetTypeName()};".encode())
    capa.ResetReading()
    for f in capa:
        h.update(str(f.GetFID()).encode())
        g = f.GetGeometryRef()
        h.update(g.ExportToIsoWkb() if g else b"")
        for i in range(f.GetFieldCount()):
            h.update(repr(f.GetField(i)).encode())
    return h.hexdigest()


def campos_a_exportar(capa, excluir):
    if not excluir:
        return None
    defn = capa.GetLayerDefn()
    return [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())
            if defn.GetFieldDefn(i).GetName() not in excluir]


def mismo_esquema(a, b):
    def firma(capa):
        d = capa.GetLayerDefn()
        return capa.GetGeomType(), [(d.GetFieldDefn(i).GetName(), d.GetFieldDefn(i).GetType())
                                    for i in range(d.GetFieldCount())]
    return firma(a) == firma(b)


def con_reintentos(funcion, *args, intentos=5):
    # GeoServer puede tener el GeoPackage bloqueado un instante mientras lee
    for n in range(1, intentos + 1):
        try:
            return funcion(*args)
        except RuntimeError as e:
            if "locked" not in str(e).lower() or n == intentos:
                raise
            time.sleep(2 * n)


def actualizar_gpkg(gdb_path, nombre, campos, gpkg, temporal):
    preparado = os.path.join(temporal, f"{nombre}.gpkg")
    gdal.VectorTranslate(preparado, gdb_path, format="GPKG", layers=[nombre], selectFields=campos,
                         geometryType="CONVERT_TO_LINEAR", preserveFID=True,
                         layerCreationOptions=["FID=OBJECTID"])
    origen = ogr.Open(preparado)
    capa_origen = origen.GetLayer(0)

    destino = ogr.Open(str(gpkg), 1) if gpkg.exists() else None
    capa_destino = destino.GetLayerByName(nombre) if destino else None
    if capa_destino is not None and mismo_esquema(capa_origen, capa_destino):
        # Mismo esquema: reemplazo de filas en una transacción, GeoServer no nota el cambio de tabla
        destino.StartTransaction()
        try:
            destino.ExecuteSQL(f'DELETE FROM "{nombre}"')
            defn = capa_destino.GetLayerDefn()
            for f in capa_origen:
                nueva = ogr.Feature(defn)
                nueva.SetFrom(f)
                nueva.SetFID(f.GetFID())
                capa_destino.CreateFeature(nueva)
            destino.CommitTransaction()
        except Exception:
            destino.RollbackTransaction()
            raise
        finally:
            destino = None
    else:
        destino = None
        modo = "overwrite" if gpkg.exists() else None
        gdal.VectorTranslate(str(gpkg), preparado, format="GPKG", accessMode=modo,
                             preserveFID=True, layerCreationOptions=["FID=OBJECTID"])
    origen = None


def actualizar_geojson(gdb_path, nombre, campos, carpeta):
    final = carpeta / f"{nombre}.geojson"
    temporal = carpeta / f"{nombre}.geojson.tmp"
    ds = gdal.VectorTranslate(str(temporal), gdb_path, format="GeoJSON", layers=[nombre],
                              selectFields=campos, dstSRS="EPSG:4326", geometryType="CONVERT_TO_LINEAR",
                              layerCreationOptions=["RFC7946=YES", "COORDINATE_PRECISION=7", "WRITE_NAME=NO"])
    ds = None
    os.replace(temporal, final)


def git_push(mensaje):
    git = shutil.which("git")
    if not git or not (RAIZ / ".git").exists():
        log.warning("git no disponible o GEOSERVER no es un repositorio: no se publica en GitHub")
        return
    run = lambda *a: subprocess.run([git, "-C", str(RAIZ), *a], capture_output=True, text=True)
    run("add", "docs")
    if run("diff", "--cached", "--quiet").returncode == 0:
        return
    run("commit", "-m", mensaje)
    r = run("push")
    if r.returncode != 0:
        log.error("git push falló: %s", r.stderr.strip())
    else:
        log.info("Publicado en GitHub")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true", help="reescribir todas las capas")
    ap.add_argument("--git", action="store_true", help="commit + push de docs/ si hubo cambios")
    args = ap.parse_args()

    cfg = cargar_config()
    gdb_path = cfg["gdb"]
    gpkg = ruta(cfg["gpkg"])
    web = ruta(cfg["web_datos"])
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    estado_path = gpkg.parent / "estado_sync.json"
    estado = json.loads(estado_path.read_text(encoding="utf-8")) if estado_path.exists() else {}

    gdb = gdal.OpenEx(gdb_path, gdal.OF_VECTOR)
    manifiesto, cambiadas = [], []
    with tempfile.TemporaryDirectory() as temporal:
        for grupo, nombre in listar_capas(cfg, gdb):
            capa = gdb.GetLayerByName(nombre)
            h = huella(capa)
            if args.forzar or estado.get(nombre, {}).get("huella") != h:
                campos = campos_a_exportar(capa, cfg["excluir_campos"])
                con_reintentos(actualizar_gpkg, gdb_path, nombre, campos, gpkg, temporal)
                actualizar_geojson(gdb_path, nombre, campos, web)
                estado[nombre] = {"huella": h, "actualizado": datetime.now().isoformat(timespec="seconds")}
                cambiadas.append(nombre)
                log.info("Actualizada %s (%d entidades)", nombre, capa.GetFeatureCount())
            srs = capa.GetSpatialRef()
            manifiesto.append({
                "id": nombre,
                "titulo": titulo_capa(nombre),
                "grupo": grupo,
                "geometria": TIPOS.get(ogr.GT_Flatten(capa.GetGeomType()), "otro"),
                "color": color_capa(nombre),
                "entidades": capa.GetFeatureCount(),
                "epsg": int(srs.GetAuthorityCode(None)) if srs and srs.GetAuthorityCode(None) else 4326,
                "archivo": f"{nombre}.geojson",
                "actualizado": estado[nombre]["actualizado"],
            })
    gdb = None

    estado_path.write_text(json.dumps(estado, indent=2), encoding="utf-8")
    if cambiadas or not (web / "capas.json").exists():
        (web / "capas.json").write_text(json.dumps(
            {"generado": datetime.now().isoformat(timespec="seconds"), "capas": manifiesto},
            ensure_ascii=False, indent=2), encoding="utf-8")

    if not cambiadas:
        log.info("Sin cambios en la GDB")
    publicar_geoserver.publicar(cfg, manifiesto, cambiadas)
    if args.git and cambiadas:
        git_push(f"Sincronización GDB {datetime.now():%Y-%m-%d %H:%M} ({len(cambiadas)} capas)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Error en la sincronización")
        raise
