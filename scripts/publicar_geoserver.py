"""Publica en GeoServer (vía REST) las capas del GeoPackage: workspace, store, capas y estilos.

Es idempotente: crea lo que falta y, para las capas modificadas, recalcula su extensión
y vacía la caché de teselas (GeoWebCache) para que los cambios se vean de inmediato.
"""
import base64
import json
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

from comun import cargar_config, configurar_log, ruta

log = configurar_log()

SLD = """<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer><Name>{nombre}</Name><UserStyle><Title>{titulo}</Title>
    <FeatureTypeStyle><Rule>{simbolo}</Rule></FeatureTypeStyle>
  </UserStyle></NamedLayer>
</StyledLayerDescriptor>"""

SIMBOLOS = {
    "poligono": """<PolygonSymbolizer>
        <Fill><CssParameter name="fill">{c}</CssParameter><CssParameter name="fill-opacity">0.35</CssParameter></Fill>
        <Stroke><CssParameter name="stroke">{c}</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
      </PolygonSymbolizer>""",
    "linea": """<LineSymbolizer>
        <Stroke><CssParameter name="stroke">{c}</CssParameter><CssParameter name="stroke-width">2</CssParameter></Stroke>
      </LineSymbolizer>""",
    "punto": """<PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
        <Fill><CssParameter name="fill">{c}</CssParameter></Fill>
        <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
      </Mark><Size>8</Size></Graphic></PointSymbolizer>""",
}


class GeoServer:
    def __init__(self, url, usuario, clave):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{usuario}:{clave}".encode()).decode()

    def pedir(self, metodo, ruta_rest, cuerpo=None, tipo="application/json"):
        if isinstance(cuerpo, dict):
            cuerpo = json.dumps(cuerpo)
        req = urllib.request.Request(
            self.url + ruta_rest, method=metodo,
            data=cuerpo.encode("utf-8") if cuerpo is not None else None,
            headers={"Authorization": self.auth, "Content-Type": tipo, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def existe(self, ruta_rest):
        return self.pedir("GET", ruta_rest)[0] == 200

    def exigir(self, metodo, ruta_rest, cuerpo=None, tipo="application/json"):
        estado, texto = self.pedir(metodo, ruta_rest, cuerpo, tipo)
        if estado >= 300:
            raise RuntimeError(f"GeoServer {metodo} {ruta_rest} -> {estado}: {texto[:300]}")
        return texto

    def disponible(self):
        try:
            return self.pedir("GET", "/rest/about/version.json")[0] == 200
        except (urllib.error.URLError, OSError):
            return False


def publicar(cfg, capas, cambiadas):
    g = cfg["geoserver"]
    ws, store = g["workspace"], g["datastore"]
    gs = GeoServer(g["url"], cfg["credenciales"]["usuario"], cfg["credenciales"]["clave"])
    if not gs.disponible():
        log.warning("GeoServer no responde en %s (o credenciales incorrectas): se omite la publicación", g["url"])
        return

    if not gs.existe(f"/rest/workspaces/{ws}"):
        gs.exigir("POST", "/rest/workspaces", {"workspace": {"name": ws}})
        log.info("Workspace %s creado", ws)

    if not gs.existe(f"/rest/workspaces/{ws}/datastores/{store}"):
        gpkg = ruta(cfg["gpkg"]).resolve().as_posix()
        gs.exigir("POST", f"/rest/workspaces/{ws}/datastores", {"dataStore": {
            "name": store,
            "connectionParameters": {"entry": [
                {"@key": "database", "$": gpkg},
                {"@key": "dbtype", "$": "geopkg"},
            ]}}})
        log.info("Almacén %s creado -> %s", store, gpkg)

    for c in capas:
        nombre = c["id"]
        if c["entidades"] == 0:
            continue  # GeoServer no puede calcular la extensión de una capa vacía
        ft = f"/rest/workspaces/{ws}/datastores/{store}/featuretypes/{nombre}"
        if not gs.existe(ft):
            gs.exigir("POST", f"/rest/workspaces/{ws}/datastores/{store}/featuretypes", {"featureType": {
                "name": nombre, "nativeName": nombre, "title": c["titulo"],
                "srs": f"EPSG:{c['epsg']}", "projectionPolicy": "FORCE_DECLARED"}})
            publicar_estilo(gs, ws, c)
            log.info("Capa publicada %s:%s", ws, nombre)
        elif nombre in cambiadas:
            gs.exigir("PUT", ft + "?recalculate=nativebbox,latlonbbox", {"featureType": {"name": nombre}})
            # vaciar la caché de teselas de la capa (404 si no tiene caché: se ignora)
            gs.pedir("POST", "/gwc/rest/masstruncate",
                     f"<truncateLayer><layerName>{ws}:{nombre}</layerName></truncateLayer>", "text/xml")
            log.info("GeoServer actualizado %s:%s", ws, nombre)


def publicar_estilo(gs, ws, c):
    nombre = c["id"]
    sld = SLD.format(nombre=nombre, titulo=escape(c["titulo"]),
                     simbolo=SIMBOLOS.get(c["geometria"], SIMBOLOS["poligono"]).format(c=c["color"]))
    if gs.existe(f"/rest/workspaces/{ws}/styles/{nombre}"):
        gs.exigir("PUT", f"/rest/workspaces/{ws}/styles/{nombre}", sld, "application/vnd.ogc.sld+xml")
    else:
        gs.exigir("POST", f"/rest/workspaces/{ws}/styles?name={nombre}", sld, "application/vnd.ogc.sld+xml")
    gs.exigir("PUT", f"/rest/layers/{ws}:{nombre}",
              {"layer": {"defaultStyle": {"name": nombre, "workspace": ws}}})


if __name__ == "__main__":
    # Publicación manual (sin sincronizar) a partir del manifiesto existente
    cfg = cargar_config()
    manifiesto = json.loads((ruta(cfg["web_datos"]) / "capas.json").read_text(encoding="utf-8"))
    publicar(cfg, manifiesto["capas"], cambiadas=[])
