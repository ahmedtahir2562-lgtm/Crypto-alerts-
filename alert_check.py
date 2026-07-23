"""
Crypto Volatility Alert Bot - Bitget version (since-last-check)
====================================================================
Runs ONCE per execution (triggered on a schedule by GitHub Actions,
e.g. every 15 minutes).

Compares each coin's current price on Bitget against the price stored from
the PREVIOUS run (price_history.json) and alerts if it moved
MOVE_THRESHOLD_PCT or more since then - not the 24h change.
"""

import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ============================== CONFIG ==============================
MOVE_THRESHOLD_PCT = 5.0          # % move since the last check that triggers an alert
ALERT_COOLDOWN_MINUTES = 60       # don't re-alert on the same coin within this window
HISTORY_FILE = "price_history.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("ALERT_EMAIL_PASSWORD")
EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", EMAIL_FROM)
# ======================================================================

BITGET_TICKERS_URL = "https://api.bitget.com/api/v2/spot/market/tickers"


def get_bitget_prices():
    """Fetch current prices for every coin on Bitget spot market.
    Returns a dict of {symbol: price}."""
    resp = requests.get(BITGET_TICKERS_URL, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", [])

    prices = {}
    for item in data:
        symbol = item.get("symbol")
        # Bitget's current/last traded price field
        price_raw = item.get("lastPr") or item.get("close")
        if symbol is None or price_raw is None:
            continue
        try:
            prices[symbol] = float(price_raw)
        except (TypeError, ValueError):
            continue
    return prices


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)


def send_email_alert(subject, body):
    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print(f"[WARN] Email not configured. Would have sent: {subject}")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        print(f"[EMAIL SENT] {subject}")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")


def main():
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    current_prices = get_bitget_prices()
    history = load_history()

    alerts_sent = 0

    for symbol, price in current_prices.items():
        prev = history.get(symbol)

        if prev is not None:
            prev_price = prev["price"]
            pct_change = (price - prev_price) / prev_price * 100

            last_alert = prev.get("last_alert")
            cooldown_ok = True
            if last_alert:
                last_alert_time = datetime.fromisoformat(last_alert)
                cooldown_ok = (now - last_alert_time).total_seconds() >= ALERT_COOLDOWN_MINUTES * 60

            if abs(pct_change) >= MOVE_THRESHOLD_PCT and cooldown_ok:
                direction = "up" if pct_change > 0 else "down"
                subject = f"[Bitget Alert] {symbol} moved {pct_change:+.2f}% ({direction})"
                body = (
                    f"{symbol} on Bitget moved {pct_change:+.2f}% since the last check.\n"
                    f"From {prev_price} to {price}.\n"
                    f"Time (UTC): {now_iso}"
                )
                print(subject)
                send_email_alert(subject, body)
                alerts_sent += 1
                history[symbol] = {"price": price, "time": now_iso, "last_alert": now_iso}
                continue

        # update stored price, keep last_alert if it exists
        history[symbol] = {
            "price": price,
            "time": now_iso,
            "last_alert": prev.get("last_alert") if prev else None,
        }

    save_history(history)
    print(f"Checked {len(current_prices)} coins on Bitget. Alerts sent this run: {alerts_sent}")


if __name__ == "__main__":
    main()
