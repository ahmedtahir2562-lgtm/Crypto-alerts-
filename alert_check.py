"""
Crypto Volatility Alert Bot - Bitget version (for GitHub Actions)
====================================================================
Runs ONCE per execution (triggered on a schedule by GitHub Actions).
Checks the 24-hour % price change for every coin available on Bitget spot
market, and emails you when any coin has moved MOVE_THRESHOLD_PCT or more.

A small cooldown file (alert_cooldown.json) is kept so the same coin
doesn't spam you repeatedly while it's still up/down a lot.
"""

import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ============================== CONFIG ==============================
MOVE_THRESHOLD_PCT = 5.0          # 24h % move that triggers an alert
ALERT_COOLDOWN_MINUTES = 60       # don't re-alert on the same coin within this window
COOLDOWN_FILE = "alert_cooldown.json"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("ALERT_EMAIL_PASSWORD")
EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", EMAIL_FROM)
# ======================================================================

BITGET_TICKERS_URL = "https://api.bitget.com/api/v2/spot/market/tickers"


def get_bitget_tickers():
    """Fetch 24h ticker data for every coin on Bitget spot market.
    Returns a list of dicts with 'symbol' and 'pct_change' (float, e.g. 5.23 for +5.23%)."""
    resp = requests.get(BITGET_TICKERS_URL, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", [])

    results = []
    for item in data:
        symbol = item.get("symbol")
        # Bitget returns the 24h change as a fraction, e.g. 0.0523 for +5.23%
        change_raw = item.get("change24h") or item.get("changeUtc24h")
        if symbol is None or change_raw is None:
            continue
        try:
            pct_change = float(change_raw) * 100
        except (TypeError, ValueError):
            continue
        results.append({"symbol": symbol, "pct_change": pct_change})
    return results


def load_cooldowns():
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f)


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
    tickers = get_bitget_tickers()
    cooldowns = load_cooldowns()

    alerts_sent = 0

    for t in tickers:
        symbol = t["symbol"]
        pct_change = t["pct_change"]

        if abs(pct_change) < MOVE_THRESHOLD_PCT:
            continue

        last_alert = cooldowns.get(symbol)
        cooldown_ok = True
        if last_alert:
            last_alert_time = datetime.fromisoformat(last_alert)
            cooldown_ok = (now - last_alert_time).total_seconds() >= ALERT_COOLDOWN_MINUTES * 60

        if not cooldown_ok:
            continue

        direction = "up" if pct_change > 0 else "down"
        subject = f"[Bitget Alert] {symbol} moved {pct_change:+.2f}% in 24h ({direction})"
        body = (
            f"{symbol} on Bitget has moved {pct_change:+.2f}% over the last 24 hours.\n"
            f"Time (UTC): {now.isoformat()}"
        )
        print(subject)
        send_email_alert(subject, body)
        alerts_sent += 1
        cooldowns[symbol] = now.isoformat()

    save_cooldowns(cooldowns)
    print(f"Checked {len(tickers)} coins on Bitget. Alerts sent this run: {alerts_sent}")


if __name__ == "__main__":
    main()
