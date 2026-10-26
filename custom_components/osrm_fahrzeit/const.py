"""Konstanten für Fahrzeit (OSRM)."""

DOMAIN = "osrm_fahrzeit"

CONF_TRACKER = "tracker"
CONF_ZIEL = "ziel"
CONF_SERVER = "server"

CONF_MIN_BEWEGUNG = "min_bewegung"
CONF_MAX_ALTER = "max_alter"
CONF_MIN_ABSTAND = "min_abstand"
CONF_PAUSE = "pause"
CONF_TAGESLIMIT = "tageslimit"
CONF_LUFTLINIE_KMH = "luftlinie_kmh"
CONF_NUR_UNTERWEGS = "nur_unterwegs"

DEFAULT_NAME = "Fahrzeit nach Hause"
DEFAULT_SERVER = "https://routing.openstreetmap.de/routed-car"

STANDARD_OPTIONEN = {
    CONF_MIN_BEWEGUNG: 500,  # Meter
    CONF_MAX_ALTER: 60,  # Minuten
    CONF_MIN_ABSTAND: 5,  # Minuten zwischen zwei Abfragen
    CONF_PAUSE: 30,  # Minuten nach einem Fehler
    CONF_TAGESLIMIT: 150,
    CONF_LUFTLINIE_KMH: 120,
    CONF_NUR_UNTERWEGS: True,
}

ATTRIBUTION = "Daten: © OpenStreetMap-Mitwirkende (ODbL)"
NACHFUEHREN_MINUTEN = 15

# Hochrechnen zwischen zwei Abfragen derselben Fahrt: Luftlinie × Umwegfaktor der letzten Route
MIN_LUFTLINIE_KM = 0.5  # darunter ist der Faktor der letzten Abfrage zu ungenau (fast am Ziel)
MAX_UMWEGFAKTOR = 6.0  # Stadtverkehr gegen 120 km/h Luftlinie liegt um 3–4
