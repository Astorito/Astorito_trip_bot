"""
Monitor de precios de LEVEL (flylevel.com) con alertas por Telegram.

Recorre las rutas/tipos de viaje configurados en config.py para los próximos N meses,
busca precios por debajo del umbral y avisa por Telegram las ofertas nuevas.

Uso:
    python monitor.py            # corrida normal: consulta, filtra y avisa
    python monitor.py --dry-run  # imprime lo parseado, NO envía Telegram ni guarda estado
    python monitor.py --test-telegram  # manda un mensaje de prueba y sale

Variables de entorno necesarias (para enviar Telegram):
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

import argparse
import calendar
import json
import os
import sys
import time
from datetime import date

import requests

import config


# ---------------------------------------------------------------------------
# Estado (anti-spam)
# ---------------------------------------------------------------------------

def load_state():
    """Devuelve {clave_oferta: precio_avisado}. Clave = ruta|triptype|fecha."""
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def offer_key(origin, dest, triptype, day):
    return f"{origin}-{dest}|{triptype}|{day}"


# ---------------------------------------------------------------------------
# Consulta al endpoint
# ---------------------------------------------------------------------------

def build_session():
    s = requests.Session()
    s.headers.update(config.HEADERS)
    return s


def fetch_calendar(session, origin, dest, triptype, year, month):
    """Pega al endpoint del calendario y devuelve el JSON (o None si falla)."""
    p = config.PARAM_NAMES
    params = {
        p["triptype"]: config.TRIPTYPE_VALUES.get(triptype, triptype),
        p["origin"]: origin,
        p["destination"]: dest,
        p["month"]: f"{month:02d}",
        p["year"]: str(year),
        p["currency"]: config.CURRENCY,
    }
    try:
        r = session.get(
            config.API_BASE, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as e:
        print(f"  ! error de red {origin}->{dest} {triptype} {year}-{month:02d}: {e}")
        return None

    if r.status_code != 200:
        print(
            f"  ! HTTP {r.status_code} en {origin}->{dest} {triptype} "
            f"{year}-{month:02d} (revisar endpoint/headers en PASO 0)"
        )
        return None

    try:
        return r.json()
    except ValueError:
        print(f"  ! respuesta no-JSON en {origin}->{dest} {triptype} {year}-{month:02d}")
        return None


# ---------------------------------------------------------------------------
# Parseo flexible del JSON -> [(fecha 'YYYY-MM-DD', precio float)]
# ---------------------------------------------------------------------------

def _looks_like_day(item):
    if not isinstance(item, dict):
        return False
    has_date = any(k in item for k in config.DATE_FIELD_CANDIDATES)
    has_price = any(k in item for k in config.PRICE_FIELD_CANDIDATES)
    return has_date and has_price


def _find_day_list(obj):
    """Busca recursivamente la primera lista de dicts con fecha + precio."""
    if isinstance(obj, list):
        if obj and any(_looks_like_day(x) for x in obj):
            return obj
        for x in obj:
            found = _find_day_list(x)
            if found:
                return found
    elif isinstance(obj, dict):
        for v in obj.values():
            found = _find_day_list(v)
            if found:
                return found
    return None


def _extract_field(item, candidates):
    for k in candidates:
        if k in item and item[k] is not None:
            return item[k]
    return None


def _extract_tags(item):
    """Devuelve la lista de tags del día (o [] si no hay)."""
    raw = _extract_field(item, config.TAGS_FIELD_CANDIDATES)
    if isinstance(raw, list):
        return [str(t).lower() for t in raw]
    if isinstance(raw, str):
        return [raw.lower()]
    return []


def parse_prices(payload):
    """Devuelve lista de (fecha_str, precio_float, tags_list) por día con precio válido."""
    days = _find_day_list(payload)
    if not days:
        return []

    out = []
    for item in days:
        if not _looks_like_day(item):
            continue
        raw_date = _extract_field(item, config.DATE_FIELD_CANDIDATES)
        raw_price = _extract_field(item, config.PRICE_FIELD_CANDIDATES)
        if raw_date is None or raw_price is None:
            continue
        # El precio puede venir anidado en un dict (p.ej. {"amount": 199}).
        if isinstance(raw_price, dict):
            raw_price = _extract_field(raw_price, config.PRICE_FIELD_CANDIDATES)
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        out.append((str(raw_date)[:10], price, _extract_tags(item)))
    return out


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _chat_ids():
    """Lista de chat_ids desde TELEGRAM_CHAT_ID (uno o varios separados por coma)."""
    raw = os.environ.get("TELEGRAM_CHAT_ID", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def send_telegram(text):
    """Envía el mensaje a todos los chat_ids. True si llegó al menos a uno."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids = _chat_ids()
    if not token or not chat_ids:
        print("  ! faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID; no se envía.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = False
    for chat_id in chat_ids:
        try:
            r = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            if r.status_code != 200:
                print(f"  ! Telegram HTTP {r.status_code} (chat {chat_id}): {r.text[:200]}")
            else:
                sent = True
        except requests.RequestException as e:
            print(f"  ! error enviando Telegram a {chat_id}: {e}")
    return sent


def booking_link(origin, dest, triptype, day):
    tt = "OW" if triptype == "OW" else "RT"
    date_nodash = day.replace("-", "")
    return (
        f"https://www.flylevel.com/es/booking/flight"
        f"?origin={origin}&destination={dest}&triptype={tt}"
        f"&departureDate={date_nodash}&adults=1"
    )


def format_alert(origin, dest, triptype, day, price, threshold, is_promo=False):
    tipo = "ida sola" if triptype == "OW" else "ida y vuelta"
    titulo = "🔥 <b>¡PROMO LEVEL!</b>" if is_promo else "✈️ <b>¡Oferta LEVEL!</b>"
    link = booking_link(origin, dest, triptype, day)
    return (
        f"{titulo}\n"
        f"<b>{origin} → {dest}</b> ({tipo})\n"
        f"📅 {day}\n"
        f"💵 <b>{price:.0f} {config.CURRENCY}</b> (umbral &lt; {threshold:.0f})\n"
        f"🔗 <a href=\"{link}\">Reservar en LEVEL</a>"
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def months_to_scan(n):
    """Devuelve [(year, month), ...] para los próximos n meses desde hoy."""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def get_threshold():
    """Umbral efectivo: ALERT_THRESHOLD (env) si existe, si no config.THRESHOLD_USD."""
    try:
        return float(os.environ.get("ALERT_THRESHOLD", config.THRESHOLD_USD))
    except ValueError:
        return float(config.THRESHOLD_USD)


def run(dry_run=False):
    session = build_session()
    state = load_state()
    threshold = get_threshold()
    new_alerts = 0
    checked = 0

    for (origin, dest) in config.ROUTES:
        for triptype in config.TRIPTYPES:
            for (year, month) in months_to_scan(config.MONTHS_AHEAD):
                checked += 1
                payload = fetch_calendar(session, origin, dest, triptype, year, month)
                time.sleep(config.REQUEST_DELAY_SECONDS)
                if payload is None:
                    continue

                for day, price, tags in parse_prices(payload):
                    is_promo = config.PROMO_TAG in tags
                    # Disparador:
                    #  - ONLY_PROMO=True  -> cualquier día con tag de promo (ignora umbral).
                    #  - ONLY_PROMO=False -> precio < umbral (la promo solo MARCA la alerta).
                    if config.ONLY_PROMO:
                        if not is_promo:
                            continue
                    else:
                        if price >= threshold:
                            continue

                    promo_txt = " [PROMO]" if is_promo else ""
                    if dry_run:
                        print(f"  [match]{promo_txt} {origin}->{dest} {triptype} {day}: {price:.0f}")
                        new_alerts += 1
                        continue

                    key = offer_key(origin, dest, triptype, day)
                    prev = state.get(key)
                    # Avisar si es nueva o si bajó respecto a lo último avisado.
                    if prev is not None and price >= float(prev):
                        continue

                    msg = format_alert(origin, dest, triptype, day, price, threshold, is_promo)
                    if send_telegram(msg):
                        state[key] = price
                        new_alerts += 1
                        print(f"  [alerta enviada]{promo_txt} {origin}->{dest} {triptype} {day}: {price:.0f}")

    if not dry_run:
        save_state(state)

    print(
        f"\nListo. Consultas: {checked}. "
        f"{'Matches' if dry_run else 'Alertas nuevas'}: {new_alerts}."
    )
    return new_alerts


def run_safe(dry_run=False):
    """Como run() pero atrapa cualquier excepción para que el loop nunca muera."""
    try:
        return run(dry_run=dry_run)
    except Exception as e:  # noqa: BLE001 - en modo 24/7 queremos seguir vivos
        print(f"  ! error en la corrida (se ignora y se sigue): {e!r}")
        return 0


def loop(interval_seconds, dry_run=False):
    """Corre indefinidamente, una pasada cada interval_seconds."""
    print(f"Modo loop: chequeando cada {interval_seconds}s. Ctrl+C para cortar.")
    while True:
        run_safe(dry_run=dry_run)
        time.sleep(interval_seconds)


def main():
    ap = argparse.ArgumentParser(description="Monitor de precios LEVEL -> Telegram")
    ap.add_argument("--dry-run", action="store_true", help="imprime matches, no envía ni guarda")
    ap.add_argument("--test-telegram", action="store_true", help="manda un mensaje de prueba y sale")
    ap.add_argument("--loop", action="store_true", help="corre 24/7 en bucle (no termina)")
    ap.add_argument(
        "--interval", type=int, default=int(os.environ.get("CHECK_INTERVAL", "180")),
        help="segundos entre chequeos en modo --loop (default 180 = 3 min, o env CHECK_INTERVAL)",
    )
    args = ap.parse_args()

    if args.test_telegram:
        ok = send_telegram("✅ Test: el bot de LEVEL está conectado a este chat.")
        sys.exit(0 if ok else 1)

    if args.loop:
        loop(args.interval, dry_run=args.dry_run)
    else:
        run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
