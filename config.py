"""
Configuración del bot de alertas de precios LEVEL (flylevel.com).

ENDPOINT: verificado y funcionando (jun-2026).
Devuelve data.dayPrices[].date/price sin auth ni rate-limit, para OW y RT.
Si LEVEL cambia la URL o los params, recapturá la request en DevTools → Network
y ajustá solo la sección ENDPOINT: el resto del código la lee de acá.
"""

# ---------------------------------------------------------------------------
# GRUPOS DE RUTAS
# Cada grupo tiene sus propias rutas, umbral y moneda.
# El env ALERT_THRESHOLD (si está seteado) sobrescribe todos los umbrales (útil para testing).
# ---------------------------------------------------------------------------

ROUTE_GROUPS = [
    {
        "name": "Europa",
        "routes": [
            ("EZE", "BCN"),
            ("BCN", "EZE"),
            ("SCL", "BCN"),
            ("BCN", "SCL"),
        ],
        "threshold": 350,
        "currency": "USD",
        "triptypes": ["OW", "RT"],
        # Si el precio baja de este valor se manda en CADA corrida (no se deduplica).
        "super_alert_threshold": 50,
    },
    {
        "name": "USA",
        # LEVEL vuela BCN ↔ LAX/SFO/BOS/EWR. Rutas directas desde EZE/SCL pueden
        # no existir — si la API devuelve vacío para una ruta, se ignora silenciosamente.
        "routes": [
            ("EZE", "LAX"), ("EZE", "SFO"), ("EZE", "BOS"), ("EZE", "EWR"),
            ("SCL", "LAX"), ("SCL", "SFO"), ("SCL", "BOS"), ("SCL", "EWR"),
        ],
        "threshold": 300,
        "currency": "EUR",
        "triptypes": ["OW", "RT"],
        "super_alert_threshold": 50,
    },
]

# ---------------------------------------------------------------------------
# VENTANA DE FECHAS
# ---------------------------------------------------------------------------

# Ventana rolling: cuántos meses hacia adelante desde hoy escanear en cada corrida.
MONTHS_AHEAD = 6

# Rangos de fechas adicionales que se escanean SIEMPRE (además de la ventana rolling).
# Formato: [("YYYY-MM-DD", "YYYY-MM-DD"), ...]
EXTRA_DATE_RANGES = [
    ("2027-03-15", "2027-05-15"),
]

# ---------------------------------------------------------------------------
# PARÁMETROS DE REQUEST
# ---------------------------------------------------------------------------

REQUEST_DELAY_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# ENDPOINT  (VERIFICADO jun-2026)
# ---------------------------------------------------------------------------

API_BASE = "https://www.flylevel.com/nwe/flights/api/calendar/"

PARAM_NAMES = {
    "triptype":    "triptype",
    "origin":      "origin",
    "destination": "destination",
    "month":       "month",
    "year":        "year",
    "currency":    "currencyCode",
}

TRIPTYPE_VALUES = {
    "OW": "OW",
    "RT": "RT",
}

DATE_FIELD_CANDIDATES  = ["date", "day", "departureDate", "fecha"]
PRICE_FIELD_CANDIDATES = ["price", "amount", "fare", "total", "precio", "value"]
TAGS_FIELD_CANDIDATES  = ["tags"]

PROMO_TAG  = "campaign"
ONLY_PROMO = False

# ---------------------------------------------------------------------------
# OTROS
# ---------------------------------------------------------------------------

BOOKING_URL = "https://www.flylevel.com/es"
STATE_FILE  = "state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer":         "https://www.flylevel.com/es",
}
