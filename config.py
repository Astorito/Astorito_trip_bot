"""
Configuración del bot de alertas de precios LEVEL (flylevel.com).

ENDPOINT: la sección "ENDPOINT" de abajo está VERIFICADA y funcionando (jun-2026).
Devuelve data.dayPrices[].date/price sin auth ni rate-limit, para OW y RT.
Si en el futuro LEVEL cambia la URL o los nombres de los parámetros, recapturá la
request en DevTools → Network y ajustá solo esta sección: el resto del código la lee de acá.
"""

# ---------------------------------------------------------------------------
# QUÉ VIGILAR
# ---------------------------------------------------------------------------

# Umbral: avisa cuando el precio de un día baja de este valor (en CURRENCY).
# Se puede sobrescribir sin tocar el código con la variable de entorno ALERT_THRESHOLD.
THRESHOLD_USD = 300

CURRENCY = "USD"

# Rutas a monitorear. Incluyo ambos sentidos para no perder ni ida ni vuelta
# cuando el tipo de viaje es one-way.
ROUTES = [
    ("EZE", "BCN"),
    ("BCN", "EZE"),
    ("SCL", "BCN"),
    ("BCN", "SCL"),
]

# Tipos de viaje: OW = one-way (solo ida), RT = round-trip (ida y vuelta).
TRIPTYPES = ["OW", "RT"]

# Cuántos meses hacia adelante escanear en cada corrida.
# Bajado a 4 para la cadencia de 3 min (menos pedidos / pasadas más rápidas / menos
# riesgo de bloqueo). Si querés cobertura anual de nuevo, poné 12.
MONTHS_AHEAD = 4

# Pausa (segundos) entre consultas, para no abusar del sitio.
REQUEST_DELAY_SECONDS = 0.5

# Timeout por request.
REQUEST_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# ENDPOINT  (VERIFICADO jun-2026)
# ---------------------------------------------------------------------------

# URL base del calendario de precios (motor de Vueling). Confirmada funcionando.
API_BASE = "https://www.flylevel.com/nwe/flights/api/calendar/"

# Nombres de los parámetros de query que espera el endpoint.
# Si en Network ves otros nombres (p.ej. "tripType" en camelCase), cambialos acá.
PARAM_NAMES = {
    "triptype": "triptype",
    "origin": "origin",
    "destination": "destination",
    "month": "month",
    "year": "year",
    "currency": "currencyCode",
}

# Valores que el endpoint espera para cada tipo de viaje.
# Algunos motores usan "OW"/"RT", otros "oneway"/"roundtrip". Ajustar si hace falta.
TRIPTYPE_VALUES = {
    "OW": "OW",
    "RT": "RT",
}

# El parser de precios (en monitor.py) busca de forma flexible cualquier lista de
# objetos que tenga un campo de fecha y uno de precio, así que normalmente NO hace
# falta tocar nada más. Estos son los nombres de campo candidatos que reconoce:
DATE_FIELD_CANDIDATES = ["date", "day", "departureDate", "fecha"]
PRICE_FIELD_CANDIDATES = ["price", "amount", "fare", "total", "precio", "value"]
TAGS_FIELD_CANDIDATES = ["tags"]

# Tag que LEVEL pone en los días con tarifa de promo/campaña. Se marca como PROMO
# en la alerta. Si querés avisar SOLO en días de promo (ignorando el umbral),
# poné ONLY_PROMO = True.
PROMO_TAG = "campaign"
ONLY_PROMO = False

# ---------------------------------------------------------------------------
# OTROS
# ---------------------------------------------------------------------------

# Link de reserva que se incluye en la alerta (informativo).
BOOKING_URL = "https://www.flylevel.com/es"

# Archivo donde se guardan las ofertas ya avisadas (anti-spam).
STATE_FILE = "state.json"

# User-Agent de navegador real: clave para evitar el 403 del front anti-bots.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.flylevel.com/es",
}
