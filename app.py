#!/usr/bin/env python3
"""
app.py - Flask backend for the Restaurant Reservation Monitor.

Run locally:
    GMAIL_FROM=you@gmail.com GMAIL_PASSWORD="xxxx" python app.py

Deploy to Railway with env vars set in the dashboard.
"""

import logging
import os
import smtplib
import threading
import uuid
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText

from flask import Flask, jsonify, render_template, request

from monitor import check_opentable, check_resy, lookup_resy_venue, parse_opentable_url

# ── Credentials (from environment variables) ──────────────────────────────────
GMAIL_FROM     = os.environ.get("GMAIL_FROM", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Shared monitor state ──────────────────────────────────────────────────────
# { monitor_id: state_dict }  — written by background threads, read by API handlers
_monitors: dict = {}
_lock = threading.Lock()

MAX_STOP_DAYS = 30  # hard cap: never monitor beyond 1 month from today


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {period}"


def _fmt_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d")


def _restaurant_url(restaurant: dict) -> str:
    if restaurant.get("url"):
        return restaurant["url"]
    if restaurant["platform"] == "opentable" and restaurant.get("rid"):
        return f"https://www.opentable.com/restaurant/profile/{restaurant['rid']}"
    return "https://resy.com"


def _send_sms(to: str, subject: str, body: str) -> None:
    if not GMAIL_FROM or not GMAIL_PASSWORD:
        log.warning("Gmail credentials missing — SMS skipped.")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_FROM
    msg["To"]      = to
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_FROM, GMAIL_PASSWORD)
            smtp.sendmail(GMAIL_FROM, to, msg.as_string())
        log.info("SMS sent to %s — %s", to, subject)
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail auth failed — check App Password.")
    except Exception as exc:
        log.error("SMS send failed: %s", exc)


def _alert_found(restaurant: dict, slots: list, sms_to: str) -> None:
    times_12h = ", ".join(_fmt_time(t) for t in slots)
    url = _restaurant_url(restaurant)
    body = (
        f"Reservation Alert: {restaurant['name']} - "
        f"A table for {restaurant['party_size']} is available on "
        f"{_fmt_date(restaurant['date'])} - grab it before its gone!\n\n"
        f"Available times: {times_12h}\n\n"
        f"Book now: {url}\n\n"
        f"Thanks for using Vidhi's reservation scraper!"
    )
    _send_sms(sms_to, f"Reservation Alert: {restaurant['name']}", body)


def _alert_expired(restaurant: dict, stop_date_str: str, sms_to: str) -> None:
    body = (
        f"No reservation found for {restaurant['name']} on "
        f"{_fmt_date(stop_date_str)}. Monitoring has ended. "
        f"- Vidhi's reservation scraper"
    )
    _send_sms(sms_to, f"Monitoring ended: {restaurant['name']}", body)


# ── Background monitor thread ─────────────────────────────────────────────────

def _monitor_thread(monitor_id: str) -> None:
    with _lock:
        state = _monitors.get(monitor_id)
    if not state:
        return

    restaurant = state["restaurant"]
    interval   = state["interval"]          # seconds
    stop_date  = datetime.strptime(state["stop_date"], "%Y-%m-%d").date()
    sms_to     = state["sms_to"]
    stop_event = state["stop_event"]
    alerted: set = set()

    log.info("[%s] Started monitoring %s", monitor_id, restaurant["name"])

    while not stop_event.is_set():
        # ── Condition 2: stop date reached ────────────────────────────────────
        if date.today() > stop_date:
            log.info("[%s] Stop date reached for %s", monitor_id, restaurant["name"])
            _alert_expired(restaurant, state["stop_date"], sms_to)
            with _lock:
                if monitor_id in _monitors:
                    _monitors[monitor_id]["status"]        = "expired"
                    _monitors[monitor_id]["status_detail"] = (
                        f"No reservation found by {_fmt_date(state['stop_date'])}"
                    )
            return

        # ── Availability check ────────────────────────────────────────────────
        try:
            slots = (
                check_resy(restaurant)
                if restaurant["platform"] == "resy"
                else check_opentable(restaurant)
            )
        except Exception as exc:
            log.error("[%s] Check error: %s", monitor_id, exc)
            slots = []

        now_str = datetime.now().strftime("%-I:%M %p")
        with _lock:
            if monitor_id in _monitors:
                _monitors[monitor_id]["last_check"] = now_str

        new_slots = [t for t in slots if t not in alerted]

        if new_slots:
            # ── Condition 1: reservation found ────────────────────────────────
            log.info("[%s] Found slots for %s: %s", monitor_id, restaurant["name"], new_slots)
            _alert_found(restaurant, new_slots, sms_to)
            for t in new_slots:
                alerted.add(t)
            with _lock:
                if monitor_id in _monitors:
                    _monitors[monitor_id]["status"]        = "found"
                    _monitors[monitor_id]["slots"]         = new_slots
                    _monitors[monitor_id]["status_detail"] = (
                        ", ".join(_fmt_time(t) for t in new_slots)
                    )
            return
        else:
            log.info("[%s] No slots for %s on %s", monitor_id, restaurant["name"], restaurant["date"])

        # Wait for next interval (interruptible by stop_event)
        stop_event.wait(interval)

    # ── Condition 3: user cancelled ───────────────────────────────────────────
    with _lock:
        if monitor_id in _monitors and _monitors[monitor_id]["status"] == "watching":
            _monitors[monitor_id]["status"] = "cancelled"
    log.info("[%s] Monitor cancelled: %s", monitor_id, restaurant["name"])


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/resolve", methods=["POST"])
def resolve():
    """Resolve a Resy or OpenTable URL to a restaurant name + ID."""
    data     = request.get_json(silent=True) or {}
    platform = data.get("platform", "")
    url      = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "URL is required."}), 400

    if platform == "resy":
        info = lookup_resy_venue(url)
        if not info:
            return jsonify({"error": "Could not resolve this Resy URL. Make sure it's a valid restaurant page."}), 400
        meta = " · ".join(filter(None, [info.get("neighborhood", ""), info.get("cuisine", "")]))
        return jsonify({
            "name":     info["name"],
            "venue_id": info["venue_id"],
            "meta":     meta,
            "url":      url.split("?")[0],
        })

    if platform == "opentable":
        info = parse_opentable_url(url)
        if not info:
            return jsonify({"error": "Could not resolve this OpenTable URL. Make sure it's a valid restaurant page."}), 400
        return jsonify({
            "name": info["name"],
            "rid":  info["rid"],
            "meta": "",
            "url":  url.split("?")[0],
        })

    return jsonify({"error": "Unknown platform."}), 400


@app.route("/api/start", methods=["POST"])
def start_monitor():
    """Start monitoring a restaurant. Returns the new monitor ID."""
    data = request.get_json(silent=True) or {}

    # Validate required fields
    for field in ["platform", "name", "date", "earliest", "latest",
                  "party_size", "phone", "frequency", "stop_date"]:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400

    phone_val = str(data["phone"]).strip()
    if len(phone_val) != 10 or not phone_val.isdigit():
        return jsonify({"error": "Phone number must be exactly 10 digits."}), 400

    # Enforce stop date cap
    max_stop = date.today() + timedelta(days=MAX_STOP_DAYS)
    try:
        stop_date = datetime.strptime(data["stop_date"], "%Y-%m-%d").date()
    except ValueError:
        stop_date = max_stop
    stop_date = min(stop_date, max_stop)

    restaurant = {
        "id":         str(uuid.uuid4())[:8],
        "name":       data["name"],
        "platform":   data["platform"],
        "venue_id":   data.get("venue_id"),
        "rid":        data.get("rid"),
        "url":        data.get("url", ""),
        "date":       data["date"],
        "earliest":   data["earliest"],
        "latest":     data["latest"],
        "party_size": int(data["party_size"]),
    }

    monitor_id = str(uuid.uuid4()).replace("-", "")[:16]
    stop_event = threading.Event()

    state = {
        "id":            monitor_id,
        "restaurant":    restaurant,
        "status":        "watching",
        "status_detail": "",
        "slots":         [],
        "last_check":    None,
        "started_at":    datetime.now().strftime("%-I:%M %p"),
        "stop_date":     stop_date.strftime("%Y-%m-%d"),
        "interval":      max(1, int(data["frequency"])) * 60,
        "sms_to":        f"{phone_val}@tmomail.net",
        "stop_event":    stop_event,
    }

    with _lock:
        _monitors[monitor_id] = state

    threading.Thread(target=_monitor_thread, args=(monitor_id,), daemon=True).start()

    return jsonify({"id": monitor_id, "name": restaurant["name"]})


@app.route("/api/monitor/<monitor_id>", methods=["DELETE"])
def stop_or_dismiss_monitor(monitor_id):
    """
    Cancel a running monitor (sets stop_event, marks cancelled), or
    remove a completed/expired/cancelled monitor from the list entirely.
    Running monitors are cancelled first; a second DELETE removes them.
    """
    with _lock:
        state = _monitors.get(monitor_id)
    if not state:
        return jsonify({"error": "Monitor not found."}), 404

    if state["status"] == "watching":
        # Still running — cancel the thread
        state["stop_event"].set()
        with _lock:
            if monitor_id in _monitors:
                _monitors[monitor_id]["status"] = "cancelled"
        log.info("[%s] Cancelled by user.", monitor_id)
    else:
        # Already done — dismiss from list
        with _lock:
            _monitors.pop(monitor_id, None)
        log.info("[%s] Dismissed by user.", monitor_id)

    return jsonify({"ok": True})


@app.route("/api/monitors", methods=["GET"])
def get_monitors():
    """Return the current state of all monitors."""
    with _lock:
        result = []
        for mid, s in list(_monitors.items()):
            r = s["restaurant"]
            result.append({
                "id":            mid,
                "name":          r["name"],
                "platform":      r["platform"],
                "date":          r["date"],
                "party_size":    r["party_size"],
                "earliest":      r["earliest"],
                "latest":        r["latest"],
                "status":        s["status"],
                "status_detail": s.get("status_detail", ""),
                "last_check":    s["last_check"],
                "started_at":    s["started_at"],
                "stop_date":     s["stop_date"],
                "url":           r.get("url", ""),
            })
    return jsonify(result)



# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
