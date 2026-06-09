# flylevel-bot

Bot que vigila el calendario de tarifas de **LEVEL** (flylevel.com) y avisa por
**Telegram** cuando aparece un precio por debajo de un umbral.

**Dos formas de correrlo:**
- **24/7 cada 3 min (recomendado)** → VM gratis de Oracle Cloud con `systemd`.
  Guía completa: **[deploy/setup-oracle.md](deploy/setup-oracle.md)**.
- **Cada ~5 min sin servidor** → GitHub Actions (ver más abajo). Nota: el cron de
  Actions no es puntual y no baja de 5 min, sirve para chequeos espaciados, no para 3 min.

Por defecto vigila **EZE⇄BCN** y **SCL⇄BCN**, one-way y round-trip, próximos 12 meses,
y avisa cuando un día baja de **300 USD**. Todo es configurable en [`config.py`](config.py).

---

## Cómo funciona

LEVEL muestra su calendario de precios consumiendo un endpoint JSON interno
(motor de Vueling) **sin login ni rate-limit**. El bot le pega periódicamente,
parsea los precios por día, filtra los que están bajo el umbral y manda la alerta.

---

## PASO 0 — Endpoint (ya verificado ✅)

El endpoint ya está **confirmado y funcionando** (jun-2026): `config.py` apunta a
`https://www.flylevel.com/nwe/flights/api/calendar/` y devuelve `data.dayPrices[].date/price`
para OW y RT, sin auth ni rate-limit. **No tenés que hacer nada acá.**

Solo si en el futuro LEVEL cambia la API (empezás a ver `HTTP 403` o 0 resultados),
recapturala así y ajustá `config.py`:

1. Abrí <https://www.flylevel.com/es> y entrá al calendario de vuelos de una ruta (ej. BCN→EZE).
2. Abrí **DevTools** (F12) → pestaña **Network** → filtro **Fetch/XHR**.
3. Cambiá de mes / hacé una búsqueda y mirá qué request se dispara (algo con
   `origin`, `destination`, `triptype`, `month`, `year`, `currency`).
4. Click derecho sobre la request → **Copy → Copy as cURL**.
5. Click en la request → pestaña **Response** → mirá el JSON.
6. Comprobá contra `config.py`:
   - `API_BASE` = la URL (sin los `?params`).
   - `PARAM_NAMES` = los nombres reales de cada parámetro de query.
   - `TRIPTYPE_VALUES` = qué string espera para one-way / round-trip.
   - El parser busca solo (no hace falta tocarlo), pero si los campos de fecha/precio
     tienen nombres raros, agregalos a `DATE_FIELD_CANDIDATES` / `PRICE_FIELD_CANDIDATES`.

Validá rápido con:

```powershell
python monitor.py --dry-run
```

Debe imprimir matches sin enviar nada. Si ves `HTTP 403` o 0 resultados, ajustá
`API_BASE` / `PARAM_NAMES` / `HEADERS` y reintentá.

---

## PASO 1 — Crear el bot de Telegram

1. En Telegram, hablá con **@BotFather** → `/newbot` → te da el **TOKEN**.
2. Mandale un mensaje cualquiera a tu bot nuevo.
3. Obtené tu **chat_id**: abrí en el navegador
   `https://api.telegram.org/bot<TOKEN>/getUpdates` y leé `result[].message.chat.id`.
4. Probá local:

```powershell
$env:TELEGRAM_TOKEN="123:ABC"; $env:TELEGRAM_CHAT_ID="111111"
python monitor.py --test-telegram
```

Tiene que llegarte un mensaje de prueba.

---

## PASO 2 — Subir a GitHub y configurar secrets

1. Creá un repo y subí esta carpeta.
2. En **Settings → Secrets and variables → Actions → New repository secret**, cargá:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Andá a la pestaña **Actions**, elegí *monitor-level* y tocá **Run workflow**
   (`workflow_dispatch`) para una corrida manual de prueba. Revisá el log.

A partir de ahí corre solo cada 30 min (ver `.github/workflows/monitor.yml`).

> **Notas de GitHub Actions:** el cron no es exacto al minuto (puede demorarse en
> horas pico) y los workflows programados **se desactivan tras 60 días sin actividad**
> en el repo — cualquier push o corrida manual los reactiva.

---

## Uso local

```powershell
pip install -r requirements.txt

python monitor.py --dry-run        # imprime matches, no envía ni guarda estado
python monitor.py --test-telegram  # manda mensaje de prueba
python monitor.py                  # corrida real (consulta, filtra y avisa)
```

## Anti-spam

`state.json` recuerda las ofertas ya avisadas: solo te llega una alerta nueva cuando
aparece una oferta que no habías visto o cuando el precio baja respecto al último avisado.
En Actions se persiste con `actions/cache`.

## Uso responsable

Es automatización personal: headers de navegador real, un pequeño delay entre consultas
y frecuencia moderada para no abusar del sitio.
