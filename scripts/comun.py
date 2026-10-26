"""Utilidades compartidas: configuración, rutas, títulos y colores de capas."""
import json
import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Color por palabra clave en el nombre de la capa (se usa en GeoServer y en el visor web)
COLORES = {
    "Afectaciones": "#e03131",
    "Energia": "#f08c00",
    "Telecomunicaciones": "#7048e8",
    "Agua": "#1971c2",
    "Gas": "#c2255c",
    "Canales": "#0ca678",
    "Infraestructura": "#495057",
}

NOMBRES = {
    "BG_Afectaciones_1": "Afectaciones prediales (BG)",
    "Energia_Electrica": "Energía eléctrica",
    "Telecomunicaciones": "Telecomunicaciones",
    "Agua_Alcantarillado": "Agua y alcantarillado",
    "Gas": "Gas",
    "Canales_Riego": "Canales de riego",
    "Infraestructura_Civil": "Infraestructura civil",
}

SUFIJOS = {"po": "polígonos", "li": "líneas", "pt": "puntos"}


def cargar_config():
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    local = RAIZ / "config.local.json"  # credenciales, fuera de git
    cfg["credenciales"] = (
        json.loads(local.read_text(encoding="utf-8"))
        if local.exists()
        else {"usuario": "admin", "clave": "geoserver"}
    )
    return cfg


def ruta(cfg_valor):
    p = Path(cfg_valor)
    return p if p.is_absolute() else RAIZ / p


def color_capa(nombre):
    for clave, color in COLORES.items():
        if clave in nombre:
            return color
    return "#343a40"


def titulo_capa(nombre):
    if nombre in NOMBRES:
        return NOMBRES[nombre]
    base = nombre.removeprefix("Inter_")
    base, _, suf = base.rpartition("_")
    if suf not in SUFIJOS:
        return nombre.replace("_", " ")
    return f"{NOMBRES.get(base, base.replace('_', ' '))} ({SUFIJOS[suf]})"


def configurar_log():
    log = logging.getLogger("redvial")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    (RAIZ / "datos").mkdir(exist_ok=True)
    archivo = logging.FileHandler(RAIZ / "datos" / "sync.log", encoding="utf-8")
    archivo.setFormatter(fmt)
    log.addHandler(archivo)
    if sys.stdout:  # pythonw (tarea programada) no tiene consola
        consola = logging.StreamHandler(sys.stdout)
        consola.setFormatter(fmt)
        log.addHandler(consola)
    return log
