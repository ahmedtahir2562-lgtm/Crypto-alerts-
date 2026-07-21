"""
Crypto Volatility Alert Bot - GitHub Actions version
=======================================================
This version runs ONCE per execution (not an infinite loop), designed to be
triggered on a schedule by GitHub Actions (e.g. every 5 minutes).

It compares the current price of each coin against the price stored from
the previous run (price_history.json) to detect big moves.

Email credentials come from environment variables, which GitHub Actions
injects from repository "Secrets" (never hardcoded here).
"""

import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ============================== CONFIG ==============================
MOVE_THRESHOLD_PCT = 5.0          # % move since the last check that triggers an alert
ALERT_COOLDOWN_MINUTES = 30       # don't re-alert on the same coin within this window
HISTORY_FILE = "price_history.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("ALERT_EMAIL_PASSWORD")
EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", EMAIL_FROM)
# ======================================================================

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"


def get_all_usdt_symbols():
    resp = requests.get(BINANCE_EXCHANGE_INFO_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [
        s["symbol"] for s in data["symbols"]
        if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
    ]


def get_prices():
    resp = requests.get(BINANCE_PRICE_URL, timeout=15)
    resp.raise_for_status()
    return {item["symbol"]: float(item["price"]) for item in resp.json()}


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

    symbols = get_all_usdt_symbols()
    current_prices = get_prices()
    history = load_history()

    alerts_sent = 0

    for symbol in symbols:
        price = current_prices.get(symbol)
        if price is None:
            continue

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
                subject = f"[Crypto Alert] {symbol} moved {pct_change:+.2f}% ({direction})"
                body = (
                    f"{symbol} moved {pct_change:+.2f}% since the last check.\n"
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
    print(f"Checked {len(symbols)} coins. Alerts sent this run: {alerts_sent}")


if __name__ == "__main__":
    main()
