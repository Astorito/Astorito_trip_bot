"""
Monitor de precios de LEVEL (flylevel.com) con alertas por Telegram.

Uso:
    python monitor.py            # corrida normal
    python monitor.py --dry-run  # imprime matches, NO envía ni guarda
    python monitor.py --test-telegram
    python monitor.py --loop     # 24/7 en bucle
"""

import argparse
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
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def offer_key(origin, dest, triptype, day, currency):
    return f"{origin}-{dest}|{triptype}|{day}|{currency}"


# ---------------------------------------------------------------------------
# Fechas a escanear
# ---------------------------------------------------------------------------

def months_rolling(n):
    """Próximos n meses desde hoy."""
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


def months_for_range(start_str, end_str):
    """Todos los (year, month) dentro del rango de fechas dado."""
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str)
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def all_months_to_scan():
    """Unión deduplicada: ventana rolling + rangos extra."""
    months = set(months_rolling(config.MONTHS_AHEAD))
    for (start_str, end_str) in config.EXTRA_DATE_RANGES:
        months.update(months_for_range(start_str, end_str))
    return sorted(months)


def date_is_in_scope(day_str):
    """True si la fecha cae en la ventana rolling O en algún rango extra."""
    try:
        d = date.fromisoformat(day_str)
    except ValueError:
        return False
    today = date.today()
    # Ventana rolling
    rolling = months_rolling(config.MONTHS_AHEAD)
    if rolling:
        last_y, last_m = rolling[-1]
        last_day = date(last_y, last_m, 28)  # margen conservador
        if today <= d <= last_day:
            return True
    # Rangos extra
    for (start_str, end_str) in config.EXTRA_DATE_RANGES:
        if date.fromisoformat(start_str) <= d <= date.fromisoformat(end_str):
            return True
    return False


# ---------------------------------------------------------------------------
# Consulta al endpoint
# ---------------------------------------------------------------------------

def build_session():
    s = requests.Session()
    s.headers.update(config.HEADERS)
    return s


def fetch_calendar(session, origin, dest, triptype, year, month, currency):
    p = config.PARAM_NAMES
    params = {
        p["triptype"]:    config.TRIPTYPE_VALUES.get(triptype, triptype),
        p["origin"]:      origin,
        p["destination"]: dest,
        p["month"]:       f"{month:02d}",
        p["year"]:        str(year),
        p["currency"]:    currency,
    }
    try:
        r = session.get(config.API_BASE, params=params, timeout=config.REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        print(f"  ! red {origin}->{dest} {triptype} {year}-{month:02d}: {e}")
        return None
    if r.status_code != 200:
        print(f"  ! HTTP {r.status_code} {origin}->{dest} {triptype} {year}-{month:02d}")
        return None
    try:
        return r.json()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Parseo
# ---------------------------------------------------------------------------

def _looks_like_day(item):
    if not isinstance(item, dict):
        return False
    return (any(k in item for k in config.DATE_FIELD_CANDIDATES) and
            any(k in item for k in config.PRICE_FIELD_CANDIDATES))


def _find_day_list(obj):
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
    raw = _extract_field(item, config.TAGS_FIELD_CANDIDATES)
    if isinstance(raw, list):
        return [str(t).lower() for t in raw]
    if isinstance(raw, str):
        return [raw.lower()]
    return []


def parse_prices(payload):
    days = _find_day_list(payload)
    if not days:
        return []
    out = []
    for item in days:
        if not _looks_like_day(item):
            continue
        raw_date  = _extract_field(item, config.DATE_FIELD_CANDIDATES)
        raw_price = _extract_field(item, config.PRICE_FIELD_CANDIDATES)
        if raw_date is None or raw_price is None:
            continue
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
    raw = os.environ.get("TELEGRAM_CHAT_ID", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def send_telegram(text):
    token    = os.environ.get("TELEGRAM_TOKEN")
    chat_ids = _chat_ids()
    if not token or not chat_ids:
        print("  ! faltan TELEGRAM_TOKEN / TELEGRAM_CHAT_ID")
        return False
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = False
    for chat_id in chat_ids:
        try:
            r = requests.post(url, json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            }, timeout=config.REQUEST_TIMEOUT_SECONDS)
            if r.status_code == 200:
                sent = True
            else:
                print(f"  ! Telegram HTTP {r.status_code} (chat {chat_id})")
        except requests.RequestException as e:
            print(f"  ! Telegram error {chat_id}: {e}")
    return sent


def booking_link(origin, dest, triptype, day):
    return (
        f"https://www.flylevel.com/es/booking/flight"
        f"?origin={origin}&destination={dest}&triptype={triptype}"
        f"&departureDate={day.replace('-','')}&adults=1"
    )


def format_alert(origin, dest, triptype, day, price, threshold, currency, is_promo=False):
    tipo   = "ida sola" if triptype == "OW" else "ida y vuelta"
    titulo = "🔥 <b>¡PROMO LEVEL!</b>" if is_promo else "✈️ <b>¡Oferta LEVEL!</b>"
    link   = booking_link(origin, dest, triptype, day)
    return (
        f"{titulo}\n"
        f"<b>{origin} → {dest}</b> ({tipo})\n"
        f"📅 {day}\n"
        f"💵 <b>{price:.0f} {currency}</b> (umbral &lt; {threshold:.0f})\n"
        f"🔗 <a href=\"{link}\">Reservar en LEVEL</a>"
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def get_threshold(group_threshold):
    """Env ALERT_THRESHOLD sobrescribe el umbral del grupo (útil para testing)."""
    env = os.environ.get("ALERT_THRESHOLD")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return float(group_threshold)


def run(dry_run=False):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Chequeando...")
    session  = build_session()
    state    = load_state()
    new_alerts = 0
    checked    = 0
    all_months = all_months_to_scan()

    for group in config.ROUTE_GROUPS:
        threshold = get_threshold(group["threshold"])
        currency  = group["currency"]

        for (origin, dest) in group["routes"]:
            for triptype in group["triptypes"]:
                for (year, month) in all_months:
                    checked += 1
                    payload = fetch_calendar(session, origin, dest, triptype, year, month, currency)
                    time.sleep(config.REQUEST_DELAY_SECONDS)
                    if payload is None:
                        continue

                    for day, price, tags in parse_prices(payload):
                        if not date_is_in_scope(day):
                            continue

                        is_promo = config.PROMO_TAG in tags
                        if config.ONLY_PROMO:
                            if not is_promo:
                                continue
                        else:
                            if price >= threshold:
                                continue

                        super_threshold = group.get("super_alert_threshold", 0)
                        is_super  = price < super_threshold
                        promo_txt = " [PROMO]" if is_promo else ""
                        super_txt = " [SUPER]" if is_super else ""

                        if dry_run:
                            print(f"  [match]{promo_txt}{super_txt} {origin}->{dest} {triptype} {day}: {price:.0f} {currency}")
                            new_alerts += 1
                            continue

                        key  = offer_key(origin, dest, triptype, day, currency)
                        prev = state.get(key)

                        if is_super:
                            # Precio extraordinariamente bajo: manda siempre, sin deduplicar.
                            pass
                        else:
                            # Precio normal: manda solo si es nueva o bajó.
                            if prev is not None and price >= float(prev):
                                continue

                        msg = format_alert(origin, dest, triptype, day, price, threshold, currency, is_promo)
                        if send_telegram(msg):
                            if not is_super:
                                state[key] = price  # solo guarda en state si no es super
                            new_alerts += 1
                            print(f"  [alerta]{promo_txt}{super_txt} {origin}->{dest} {triptype} {day}: {price:.0f} {currency}")

    if not dry_run:
        save_state(state)

    print(f"\nListo. Consultas: {checked}. {'Matches' if dry_run else 'Alertas nuevas'}: {new_alerts}.")
    return new_alerts


def run_safe(dry_run=False):
    try:
        return run(dry_run=dry_run)
    except Exception as e:
        print(f"  ! error en la corrida (se sigue): {e!r}")
        return 0


def loop(interval_seconds, dry_run=False):
    print(f"Modo loop: chequeando cada {interval_seconds}s. Ctrl+C para cortar.")
    while True:
        run_safe(dry_run=dry_run)
        time.sleep(interval_seconds)


def main():
    ap = argparse.ArgumentParser(description="Monitor de precios LEVEL -> Telegram")
    ap.add_argument("--dry-run",       action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--loop",          action="store_true")
    ap.add_argument("--interval", type=int,
                    default=int(os.environ.get("CHECK_INTERVAL", "180")))
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
