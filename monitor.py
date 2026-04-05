#!/usr/bin/env python3
"""
Restaurant Reservation Monitor
================================
Interactively configure restaurants to watch, then polls Resy and OpenTable
and sends SMS alerts via Gmail SMTP → T-Mobile email gateway.

Usage:
    pip install requests
    python monitor.py

During monitoring, type  'stop <id>'  to drop a restaurant without quitting.
Stop the whole script with Ctrl-C.
"""

import queue
import smtplib
import threading
import time
import logging
from datetime import datetime, date
from email.mime.text import MIMEText
from pathlib import Path

import requests

# Credentials are loaded from config.py (gitignored).
# Copy config.example.py → config.py and fill in your values before running.
try:
    from config import GMAIL_FROM, GMAIL_PASSWORD, SMS_TO
except ImportError:
    # config.py is gitignored; credentials come from Streamlit secrets when
    # used via app.py, or from env vars. CLI users need to create config.py.
    GMAIL_FROM = GMAIL_PASSWORD = SMS_TO = ""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _setup_file_logging(session_start: datetime) -> Path:
    """Add a file handler that writes every log record to a dated log file."""
    log_dir  = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"monitor_{session_start.strftime('%Y%m%d_%H%M%S')}.log"

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(fh)
    return log_path

# Resy's public API key — embedded in the resy.com web app; no account needed
# for read-only availability queries.
_RESY_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"


# ── Venue search ──────────────────────────────────────────────────────────────

def lookup_resy_venue(url: str):
    """
    Given a Resy venue URL (e.g. https://resy.com/cities/new-york-ny/venues/lilia),
    extract the slug + location and return {venue_id, name, neighborhood, cuisine}
    or None on failure.
    """
    import re
    m = re.search(r"/cities/([^/]+)/venues/([^/?#]+)", url)
    if not m:
        return None
    location, slug = m.group(1), m.group(2)
    try:
        resp = requests.get(
            "https://api.resy.com/3/venue",
            headers={
                "Authorization": f'ResyAPI api_key="{_RESY_API_KEY}"',
                "X-Origin":      "https://resy.com",
                "Referer":       "https://resy.com/",
                "User-Agent":    (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            },
            params={"url_slug": slug, "location": location},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Resy venue lookup error: %s", exc)
        return None

    venue_id = data.get("id", {}).get("resy")
    if not venue_id:
        return None
    return {
        "venue_id":     venue_id,
        "name":         data.get("name", slug),
        "neighborhood": data.get("location", {}).get("neighborhood", ""),
        "cuisine":      data.get("type", ""),
    }


def search_resy(query: str) -> list:
    """
    Search Resy for venues in NYC matching query.
    Returns a list of dicts: {name, venue_id, neighborhood, cuisine}.
    """
    try:
        resp = requests.get(
            "https://api.resy.com/3/venues",
            headers={
                "Authorization": f'ResyAPI api_key="{_RESY_API_KEY}"',
                "X-Origin":      "https://resy.com",
                "Referer":       "https://resy.com/",
                "User-Agent":    (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            },
            params={
                "query":     query,
                "city_code": "NY",
                "per_page":  8,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Resy search error: %s", exc)
        return []

    results = []
    for item in data.get("results", {}).get("venues", [])[:8]:
        vid = item.get("id", {}).get("resy")
        if not vid:
            continue
        results.append({
            "name":         item.get("name", ""),
            "venue_id":     vid,
            "neighborhood": item.get("location", {}).get("neighborhood", ""),
            "cuisine":      item.get("type", ""),
        })
    return results


def search_opentable(query: str) -> list:
    """
    Search OpenTable for restaurants in NYC matching query.
    Returns a list of dicts: {name, rid, neighborhood, cuisine}.
    """
    try:
        resp = requests.get(
            "https://mobile-api.opentable.com/api/v2/restaurant/search",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
            params={
                "term":      query,
                "latitude":  40.7128,
                "longitude": -74.0060,
                "radius":    10,
                "pageSize":  8,
                "covers":    2,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("OpenTable search error: %s", exc)
        return []

    results = []
    for r in data.get("restaurants", [])[:8]:
        rid = r.get("rid") or r.get("id")
        if not rid:
            continue
        results.append({
            "name":         r.get("name", ""),
            "rid":          int(rid),
            "neighborhood": r.get("neighborhood", r.get("city", "")),
            "cuisine":      r.get("cuisine_type", r.get("cuisineType", "")),
        })
    return results

_RESY_HEADERS = {
    "Authorization": f'ResyAPI api_key="{_RESY_API_KEY}"',
    "X-Origin":      "https://resy.com",
    "Referer":       "https://resy.com/",
    "User-Agent":    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_OT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":       "application/json, text/plain, */*",
    "Referer":      "https://www.opentable.com/",
    "Content-Type": "application/json",
}

# Tracks (restaurant id, date, time) tuples we've already sent alerts for.
_alerted: set = set()

# Queue for live commands typed during monitoring (e.g. "stop 3").
_cmd_queue: queue.Queue = queue.Queue()

# Restaurants awaiting a yes/no stop-confirmation after a reservation was found.
# Maps restaurant["id"] → restaurant dict, in insertion order.
_pending_confirm: dict = {}


# ── Interactive setup ─────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    """Prompt the user and return stripped input; use default if blank."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw if raw else default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"  Please enter a whole number.")


def _ask_date(prompt: str) -> str:
    """Prompt for a date in YYYY-MM-DD format; keep asking until valid."""
    while True:
        raw = _ask(prompt)
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            print("  Invalid date. Use YYYY-MM-DD (e.g. 2025-02-14).")


def _ask_time(prompt: str, default: str) -> str:
    """Prompt for a time in HH:MM (24-h) format; keep asking until valid."""
    while True:
        raw = _ask(prompt, default)
        try:
            datetime.strptime(raw, "%H:%M")
            return raw
        except ValueError:
            print("  Invalid time. Use HH:MM in 24-h format (e.g. 18:00).")


def _ask_platform() -> str:
    """Prompt for platform choice; return 'resy' or 'opentable'."""
    while True:
        raw = _ask("  Platform (resy / opentable)").lower()
        if raw in ("resy", "opentable"):
            return raw
        print("  Please type 'resy' or 'opentable'.")


def _ask_stop_date() -> date:
    """Prompt for a monitoring stop date in MM/DD/YY; keep asking until valid."""
    while True:
        raw = _ask("Stop monitoring after date (MM/DD/YY, e.g. 04/10/26)")
        try:
            return datetime.strptime(raw, "%m/%d/%y").date()
        except ValueError:
            print("  Invalid date. Use MM/DD/YY (e.g. 04/10/26).")


def _collect_restaurants() -> tuple:
    """Collect restaurant entries and monitoring settings. Returns (restaurants, interval_mins, stop_date)."""
    print("\n" + "=" * 60)
    print("  Restaurant Reservation Monitor — Setup")
    print("=" * 60)
    print(
        "\nFor Resy venue IDs, visit:\n"
        "  https://api.resy.com/3/venue/find?query=NAME&geo[city]=New+York\n"
        "  and look for the 'resy' numeric ID in the JSON.\n"
        "For OpenTable restaurant IDs, check the URL:\n"
        "  opentable.com/r/...-new-york?rid=XXXXX\n"
    )

    restaurants = []
    next_id = 1

    while True:
        print(f"─── Restaurant #{next_id} ───────────────────────────────────")
        name     = _ask("  Name")
        platform = _ask_platform()

        if platform == "resy":
            venue_id = _ask_int("  Resy venue_id", 0)
            rid = None
        else:
            rid      = _ask_int("  OpenTable rid", 0)
            venue_id = None

        res_date   = _ask_date("  Date to check (YYYY-MM-DD)")
        earliest   = _ask_time("  Earliest time slot (HH:MM, 24-h)", "18:00")
        latest     = _ask_time("  Latest time slot  (HH:MM, 24-h)", "22:00")
        party_size = _ask_int("  Party size", 2)

        entry = {
            "id":         next_id,
            "name":       name,
            "platform":   platform,
            "venue_id":   venue_id,
            "rid":        rid,
            "date":       res_date,
            "earliest":   earliest,
            "latest":     latest,
            "party_size": party_size,
        }
        restaurants.append(entry)
        print(f"  Added: [{next_id}] {name} ({platform}) on {res_date}")
        next_id += 1

        another = _ask("\nAdd another restaurant? (yes / no)", "no").lower()
        if another not in ("yes", "y"):
            break
        print()

    print("\n─── Monitoring settings ────────────────────────────────────")
    interval_mins = _ask_int("Check every N minutes", 5)
    stop_date     = _ask_stop_date()

    return restaurants, interval_mins, stop_date


def _print_summary(restaurants: list, interval_mins: int, stop_date: date) -> None:
    """Print a formatted confirmation summary of everything that will be monitored."""
    col = 62
    print("\n" + "=" * col)
    print("  CONFIRMATION SUMMARY")
    print("=" * col)
    print(f"  {'#':<4} {'Restaurant':<22} {'Platform':<11} {'ID':<8} {'Date':<12} {'Window':<13} Party")
    print("  " + "─" * (col - 2))
    for r in restaurants:
        pid    = r["venue_id"] if r["platform"] == "resy" else r["rid"]
        window = f"{r['earliest']}–{r['latest']}"
        print(
            f"  [{r['id']:<2}] {r['name']:<22} {r['platform']:<11} {str(pid):<8} "
            f"{r['date']:<12} {window:<13} {r['party_size']}"
        )
    print("  " + "─" * (col - 2))
    print(f"  Check interval : every {interval_mins} minute(s)")
    print(f"  Auto-stop after: {stop_date.strftime('%m/%d/%y')}")
    print(f"  SMS recipient  : {SMS_TO}")
    print("=" * col)


def prompt_setup() -> tuple:
    """
    Interactively collect all monitoring parameters, show a confirmation summary,
    and loop until the user confirms or chooses to re-enter.

    Returns:
        restaurants  — list of restaurant dicts
        interval     — check interval in seconds
        stop_date    — date object after which monitoring halts
    """
    while True:
        restaurants, interval_mins, stop_date = _collect_restaurants()
        _print_summary(restaurants, interval_mins, stop_date)

        confirm = _ask("\nEverything look right? Start monitoring? (yes / no)", "yes").lower()
        if confirm in ("yes", "y"):
            break
        print("\nStarting over — please re-enter your settings.\n")

    print(
        "\nMonitoring started. Type  'stop <id>'  to remove a restaurant.\n"
        "Press Ctrl-C to quit entirely.\n"
    )
    return restaurants, interval_mins * 60, stop_date


# ── Alert ─────────────────────────────────────────────────────────────────────

def send_alert(restaurant: dict, slots: list) -> None:
    """Send an SMS alert via Gmail SMTP → T-Mobile email gateway."""
    times_str = ", ".join(slots)
    body = (
        f"{restaurant['name']} ({restaurant['platform']}) has openings on "
        f"{restaurant['date']}: {times_str} for {restaurant['party_size']}. Book now!"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"Reservation open: {restaurant['name']}"
    msg["From"]    = GMAIL_FROM
    msg["To"]      = SMS_TO

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_FROM, GMAIL_PASSWORD)
            smtp.sendmail(GMAIL_FROM, SMS_TO, msg.as_string())
        log.info("SMS sent  — [%d] %s on %s: %s", restaurant["id"], restaurant["name"], restaurant["date"], times_str)
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Gmail authentication failed. Make sure GMAIL_PASSWORD is a Google "
            "App Password (myaccount.google.com/apppasswords), not your account password."
        )
    except Exception as exc:
        log.error("Failed to send SMS alert: %s", exc)


# ── API checks ────────────────────────────────────────────────────────────────

def check_resy(restaurant: dict) -> list:
    """Return sorted available 'HH:MM' slots for a Resy venue."""
    try:
        resp = requests.get(
            "https://api.resy.com/4/find",
            headers=_RESY_HEADERS,
            params={
                "lat":        40.7128,
                "long":       -74.0060,
                "day":        restaurant["date"],
                "party_size": restaurant["party_size"],
                "venue_id":   restaurant["venue_id"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        log.warning("Resy HTTP %s for [%d] %s", exc.response.status_code, restaurant["id"], restaurant["name"])
        return []
    except Exception as exc:
        log.warning("Resy error for [%d] %s: %s", restaurant["id"], restaurant["name"], exc)
        return []

    slots = []
    for venue in data.get("results", {}).get("venues", []):
        for slot in venue.get("slots", []):
            # "2025-02-14 19:00:00" → "19:00"
            start = slot.get("date", {}).get("start", "")
            if not start:
                continue
            hhmm = start.split(" ")[-1][:5]
            if restaurant["earliest"] <= hhmm <= restaurant["latest"]:
                slots.append(hhmm)
    return sorted(set(slots))


def check_opentable(restaurant: dict) -> list:
    """Return sorted available 'HH:MM' slots for an OpenTable restaurant."""
    payload = {
        "operationName": "RestaurantsAvailability",
        "variables": {
            "onlineReservationsInput": [
                {
                    "restaurantId":   restaurant["rid"],
                    "partySize":      restaurant["party_size"],
                    "dateTime":       f"{restaurant['date']}T{restaurant['earliest']}",
                    "databaseRegion": "NA",
                }
            ]
        },
        "query": (
            "query RestaurantsAvailability($onlineReservationsInput: [OnlineReservationsInput!]!) {"
            "  onlineReservations(input: $onlineReservationsInput) {"
            "    restaurantId"
            "    availability {"
            "      dateTime"
            "    }"
            "  }"
            "}"
        ),
    }

    try:
        resp = requests.post(
            "https://www.opentable.com/dapi/fe/gql",
            json=payload,
            headers=_OT_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        log.warning("OpenTable HTTP %s for [%d] %s", exc.response.status_code, restaurant["id"], restaurant["name"])
        return []
    except Exception as exc:
        log.warning("OpenTable error for [%d] %s: %s", restaurant["id"], restaurant["name"], exc)
        return []

    if "errors" in data:
        for err in data["errors"]:
            log.warning("OpenTable GraphQL error for [%d] %s: %s", restaurant["id"], restaurant["name"], err.get("message"))
        return []

    slots = []
    for entry in data.get("data", {}).get("onlineReservations", []):
        for avail in entry.get("availability", []):
            dt = avail.get("dateTime", "")   # "2025-02-14T19:00:00"
            if "T" not in dt:
                continue
            hhmm = dt.split("T")[-1][:5]
            if restaurant["earliest"] <= hhmm <= restaurant["latest"]:
                slots.append(hhmm)
    return sorted(set(slots))


# ── Poll loop ─────────────────────────────────────────────────────────────────

def run_checks(restaurants: list) -> None:
    """Run one check cycle across all active restaurants."""
    for restaurant in restaurants:
        platform = restaurant["platform"]
        if platform == "resy":
            slots = check_resy(restaurant)
        else:
            slots = check_opentable(restaurant)

        name = restaurant["name"]
        rid  = restaurant["id"]

        if not slots:
            log.info("No availability  — [%d] %s on %s", rid, name, restaurant["date"])
            continue

        new_slots = [t for t in slots if (rid, restaurant["date"], t) not in _alerted]

        if new_slots:
            send_alert(restaurant, new_slots)
            for t in new_slots:
                _alerted.add((rid, restaurant["date"], t))
            # Prompt the user (non-blocking) to optionally stop this restaurant.
            if rid not in _pending_confirm:
                _pending_confirm[rid] = restaurant
                print(
                    f"\n>>> Reservation found for [{rid}] {name} on {restaurant['date']}: "
                    f"{', '.join(new_slots)}"
                    f"\n    Stop monitoring this restaurant? (yes / no): ",
                    end="", flush=True,
                )
                log.info("Awaiting stop-confirmation from user for [%d] %s.", rid, name)
        else:
            log.info(
                "Available (already alerted) — [%d] %s on %s: %s",
                rid, name, restaurant["date"], ", ".join(slots),
            )


def _stdin_reader() -> None:
    """Daemon thread: read lines from stdin and put them on _cmd_queue."""
    while True:
        try:
            line = input()
            _cmd_queue.put(line.strip())
        except EOFError:
            break


def _process_commands(restaurants: list) -> list:
    """
    Drain _cmd_queue and handle:
      - 'stop <id>'       — immediately remove a restaurant
      - 'yes' / 'no'      — respond to the oldest pending stop-confirmation
    Returns the (possibly shorter) restaurants list.
    """
    while not _cmd_queue.empty():
        cmd   = _cmd_queue.get_nowait().strip()
        parts = cmd.lower().split()
        if not parts:
            continue

        # ── "stop <id>" ────────────────────────────────────────────────────────
        if len(parts) == 2 and parts[0] == "stop":
            try:
                target_id = int(parts[1])
            except ValueError:
                log.warning("Unrecognized command: '%s'  (usage: stop <id>)", cmd)
                continue
            before = len(restaurants)
            restaurants = [r for r in restaurants if r["id"] != target_id]
            _pending_confirm.pop(target_id, None)
            if len(restaurants) < before:
                log.info(
                    "Removed [%d] from watch list at %s.",
                    target_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            else:
                log.warning("No restaurant with id %d found.", target_id)

        # ── yes / no — answer the oldest pending confirmation ─────────────────
        elif parts[0] in ("yes", "y", "no", "n") and _pending_confirm:
            confirmed_id = next(iter(_pending_confirm))
            r = _pending_confirm.pop(confirmed_id)
            if parts[0] in ("yes", "y"):
                restaurants = [r2 for r2 in restaurants if r2["id"] != confirmed_id]
                log.info(
                    "User confirmed stop for [%d] %s at %s — removed from watch list.",
                    confirmed_id, r["name"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            else:
                log.info("User chose to keep monitoring [%d] %s.", confirmed_id, r["name"])
            # If another restaurant is waiting for confirmation, surface its prompt.
            if _pending_confirm:
                next_id = next(iter(_pending_confirm))
                nr = _pending_confirm[next_id]
                print(
                    f"\n>>> Stop monitoring [{next_id}] {nr['name']}? (yes / no): ",
                    end="", flush=True,
                )

        else:
            log.warning(
                "Unrecognized command: '%s'  "
                "(usage: stop <id>  |  yes/no for pending reservation prompts)", cmd,
            )

    return restaurants


def main() -> None:
    session_start = datetime.now()
    restaurants, interval, stop_date = prompt_setup()

    # Set up file logging — every log.info/warning/error goes to this file too.
    log_path = _setup_file_logging(session_start)
    print(f"Logging to: {log_path}\n")

    # Write the full session config to the log so the history is self-contained.
    log.info("=" * 60)
    log.info("Session started at %s", session_start.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Check interval : %ds", interval)
    log.info("Auto-stop after: %s", stop_date.strftime("%m/%d/%y"))
    log.info("SMS recipient  : %s", SMS_TO)
    for r in restaurants:
        pid = r["venue_id"] if r["platform"] == "resy" else r["rid"]
        log.info(
            "Watching [%d] %s  platform=%s  id=%s  date=%s  window=%s-%s  party=%d",
            r["id"], r["name"], r["platform"], pid,
            r["date"], r["earliest"], r["latest"], r["party_size"],
        )
    log.info("=" * 60)

    # Start background thread to read stdin commands without blocking the poll loop.
    t = threading.Thread(target=_stdin_reader, daemon=True)
    t.start()

    log.info(
        "Monitor running — %d restaurant(s), checking every %ds, stopping after %s.",
        len(restaurants), interval, stop_date.strftime("%m/%d/%y"),
    )

    try:
        while True:
            # Auto-stop after stop_date
            if date.today() > stop_date:
                log.info("Stop date %s reached. Exiting.", stop_date.strftime("%m/%d/%y"))
                break

            # Process any live commands (e.g. "stop 2")
            restaurants = _process_commands(restaurants)

            if not restaurants:
                log.info("No restaurants left to monitor. Exiting.")
                break

            run_checks(restaurants)

            log.info("Sleeping %ds…", interval)
            # Sleep in short increments so commands are processed promptly.
            elapsed = 0
            while elapsed < interval:
                time.sleep(5)
                elapsed += 5
                restaurants = _process_commands(restaurants)
                if not restaurants:
                    log.info("No restaurants left to monitor. Exiting.")
                    return
                if date.today() > stop_date:
                    log.info("Stop date %s reached. Exiting.", stop_date.strftime("%m/%d/%y"))
                    return

    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
