#!/usr/bin/env python3
"""
app.py — Streamlit frontend for the Restaurant Reservation Monitor.

Run with:
    streamlit run app.py

The monitoring loop runs in a background thread.  When monitoring is active
the page auto-refreshes every 4 seconds so the status stays live.
"""

import smtplib
import threading
import time
import sys
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import streamlit as st

# ── project imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from monitor import check_resy, check_opentable

try:
    from config import GMAIL_FROM, GMAIL_PASSWORD
except ImportError:
    GMAIL_FROM = GMAIL_PASSWORD = ""

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reservation Monitor",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Base ── */
html, body { background: #07070f !important; }
.stApp, .main { background: #07070f !important; font-family: 'Inter', system-ui, sans-serif !important; }
.main .block-container { padding: 2rem 3rem 4rem !important; max-width: 1300px !important; }
div[data-testid="stHeader"] { background: transparent !important; }
div[data-testid="stToolbar"] { display: none !important; }

/* ── Typography ── */
h1, h2, h3, h4, h5, h6, p, span, label { font-family: 'Inter', system-ui, sans-serif !important; }
.stMarkdown p { color: #7070a0; margin: 0; }

/* ── Widget labels ── */
.stTextInput label, .stNumberInput label, .stSelectbox label,
.stDateInput label, .stTextArea label {
    color: #6060a0 !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
}

/* ── Text inputs ── */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
    background: #10102a !important;
    border: 1.5px solid #1e1e3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.9rem !important;
    transition: border-color 0.2s !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.12) !important;
    outline: none !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    background: #10102a !important;
    border: 1.5px solid #1e1e3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
}
.stSelectbox > div > div:focus-within { border-color: #7c3aed !important; }

/* ── Date input ── */
.stDateInput input {
    background: #10102a !important;
    border: 1.5px solid #1e1e3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
}

/* ── Number input arrows ── */
.stNumberInput button {
    background: #10102a !important;
    border-color: #1e1e3a !important;
    color: #7070a0 !important;
}

/* ── Primary buttons ── */
.stButton button[kind="primary"],
button.css-7ym5gk, button.css-1x8cf1d {
    background: linear-gradient(135deg, #7c3aed 0%, #4338ca 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.01em !important;
    padding: 0.55rem 1.4rem !important;
    box-shadow: 0 2px 16px rgba(124,58,237,0.35) !important;
    transition: all 0.18s ease !important;
}
.stButton button[kind="primary"]:hover {
    background: linear-gradient(135deg, #8b4cf6 0%, #5046e5 100%) !important;
    box-shadow: 0 4px 24px rgba(124,58,237,0.55) !important;
    transform: translateY(-1px) !important;
}

/* ── Secondary buttons ── */
.stButton button:not([kind="primary"]) {
    background: #0e0e22 !important;
    border: 1.5px solid #1e1e38 !important;
    border-radius: 10px !important;
    color: #7878aa !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    transition: all 0.18s ease !important;
}
.stButton button:not([kind="primary"]):hover {
    border-color: #7c3aed !important;
    color: #c4b5fd !important;
    background: #120c28 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: #0c0c20 !important;
    border: 1px solid #1a1a30 !important;
    border-radius: 10px !important;
    color: #7070a0 !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
.streamlit-expanderContent {
    background: #09091a !important;
    border: 1px solid #1a1a30 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
}

/* ── Divider ── */
hr { border-color: #13132a !important; margin: 1.2rem 0 !important; }

/* ── Success / Error alerts ── */
.stAlert { border-radius: 10px !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #07070f; }
::-webkit-scrollbar-thumb { background: #1e1e38; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7c3aed; }

/* ── Streamlit columns gap ── */
div[data-testid="column"] { padding: 0 0.6rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Module-level monitoring state ─────────────────────────────────────────────
# Lives at module scope so the background thread and Streamlit reruns share it.
_lock = threading.Lock()
_ms = {
    "active":      False,
    "stop_event":  threading.Event(),
    "restaurants": [],          # live list; background thread reads this each cycle
    "log":         [],          # [{"ts", "level", "msg"}, ...]
    "alerted":     set(),       # (rid, date, slot_time) triples
    "found":       {},          # rid → {"restaurant": ..., "slots": [...]}
}
_MAX_LOG = 300


def _log(level: str, msg: str):
    with _lock:
        _ms["log"].append({
            "ts":    datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "msg":   msg,
        })
        if len(_ms["log"]) > _MAX_LOG:
            _ms["log"] = _ms["log"][-_MAX_LOG:]


# ── SMS ───────────────────────────────────────────────────────────────────────
def _send_sms(restaurant: dict, slots: list, sms_to: str):
    if not GMAIL_FROM or not GMAIL_PASSWORD:
        _log("WARN", "Gmail credentials missing in config.py — SMS skipped.")
        return
    body = (
        f"{restaurant['name']} ({restaurant['platform']}) has openings on "
        f"{restaurant['date']}: {', '.join(slots)} "
        f"for {restaurant['party_size']}. Book now!"
    )
    msg = MIMEText(body)
    msg["Subject"] = f"Reservation open: {restaurant['name']}"
    msg["From"]    = GMAIL_FROM
    msg["To"]      = sms_to
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_FROM, GMAIL_PASSWORD)
            smtp.sendmail(GMAIL_FROM, sms_to, msg.as_string())
        _log("INFO", f"SMS sent → {sms_to}")
    except smtplib.SMTPAuthenticationError:
        _log("ERROR", "Gmail auth failed — check App Password in config.py.")
    except Exception as exc:
        _log("ERROR", f"SMS failed: {exc}")


# ── Monitor thread ────────────────────────────────────────────────────────────
def _monitor_loop(interval: int, stop_date: date, sms_to: str):
    _log("INFO", f"Monitoring started — every {interval}s, until {stop_date}.")
    while not _ms["stop_event"].is_set():
        if date.today() > stop_date:
            _log("INFO", "Stop date reached. Monitoring ended automatically.")
            break

        with _lock:
            current = list(_ms["restaurants"])
        if not current:
            _log("INFO", "Watch list is empty. Monitoring ended.")
            break

        for r in current:
            rid = r["id"]
            if rid in _ms["found"]:
                continue  # waiting for user yes/no in the UI

            try:
                slots = check_resy(r) if r["platform"] == "resy" else check_opentable(r)
            except Exception as exc:
                _log("ERROR", f"[{rid}] {r['name']} check error: {exc}")
                continue

            with _lock:
                new_slots = [t for t in slots if (rid, r["date"], t) not in _ms["alerted"]]

            if not slots:
                _log("INFO", f"[{rid}] {r['name']} — no availability on {r['date']}")
            elif new_slots:
                _log("FOUND", f"[{rid}] {r['name']} — {', '.join(new_slots)} on {r['date']} 🎉")
                _send_sms(r, new_slots, sms_to)
                with _lock:
                    for t in new_slots:
                        _ms["alerted"].add((rid, r["date"], t))
                    _ms["found"][rid] = {"restaurant": r, "slots": new_slots}
            else:
                _log("INFO", f"[{rid}] {r['name']} — slots available (already alerted)")

        _ms["stop_event"].wait(interval)

    _ms["active"] = False
    _log("INFO", "Monitor stopped.")


def _start(restaurants: list, interval: int, stop_date: date, sms_to: str):
    _ms["stop_event"].clear()
    with _lock:
        _ms["restaurants"] = list(restaurants)
        _ms["log"]    = []
        _ms["alerted"] = set()
        _ms["found"]   = {}
    _ms["active"] = True
    threading.Thread(
        target=_monitor_loop,
        args=(interval, stop_date, sms_to),
        daemon=True,
    ).start()


def _stop_all():
    _ms["stop_event"].set()
    _ms["active"] = False
    with _lock:
        _ms["restaurants"] = []
    _log("INFO", "All monitoring stopped by user.")


def _remove(rid: int, name: str):
    with _lock:
        _ms["restaurants"] = [r for r in _ms["restaurants"] if r["id"] != rid]
        _ms["found"].pop(rid, None)
    _log("INFO", f"[{rid}] {name} removed from watch list.")


# ── Session state ─────────────────────────────────────────────────────────────
if "queue" not in st.session_state:
    st.session_state.queue   = []
    st.session_state.next_id = 1
    st.session_state.error   = ""
    st.session_state.success = ""


# ── Small UI helpers ──────────────────────────────────────────────────────────
def _section(title: str, icon: str = ""):
    label = f"{icon}  {title}" if icon else title
    st.markdown(
        f'<p style="color:#5050a0;font-size:0.68rem;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.12em;margin:0 0 0.7rem 2px;">'
        f'{label}</p>',
        unsafe_allow_html=True,
    )


def _badge(text: str, bg: str, fg: str):
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 9px;'
        f'border-radius:999px;font-size:0.7rem;font-weight:700;'
        f'letter-spacing:0.04em;white-space:nowrap;">{text}</span>'
    )


def _card_open(bg: str = "#0c0c20", border: str = "#18183a"):
    st.markdown(
        f'<div style="background:{bg};border:1px solid {border};'
        f'border-radius:14px;padding:1.3rem 1.5rem 1rem;">',
        unsafe_allow_html=True,
    )


def _card_close():
    st.markdown("</div>", unsafe_allow_html=True)


# ── Render: header ─────────────────────────────────────────────────────────────
def render_header():
    active = _ms["active"]
    dot    = (
        '<span style="display:inline-block;width:8px;height:8px;background:#4ade80;'
        'border-radius:50%;box-shadow:0 0 8px #4ade8088;margin-right:6px;"></span>'
        '<span style="color:#4ade80;font-size:0.78rem;font-weight:600;">LIVE</span>'
    ) if active else ""

    st.markdown(f"""
    <div style="padding:2rem 0 1.4rem;border-bottom:1px solid #12122a;margin-bottom:2rem;">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:14px;">
          <div style="width:46px;height:46px;
                      background:linear-gradient(135deg,#7c3aed,#4338ca);
                      border-radius:13px;display:flex;align-items:center;
                      justify-content:center;font-size:1.4rem;
                      box-shadow:0 4px 20px rgba(124,58,237,0.4);">🍽️</div>
          <div>
            <h1 style="margin:0;font-size:1.8rem;font-weight:700;
                       background:linear-gradient(135deg,#a78bfa 20%,#60a5fa 100%);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                       line-height:1.15;">
              Reservation Monitor
            </h1>
            <p style="margin:0;color:#404070;font-size:0.82rem;letter-spacing:0.02em;">
              Resy &amp; OpenTable &nbsp;·&nbsp; NYC &nbsp;·&nbsp; SMS alerts
            </p>
          </div>
        </div>
        <div>{dot}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Render: add-restaurant form ────────────────────────────────────────────────
def render_add_form():
    _section("Add Restaurant", "＋")

    r1c1, r1c2 = st.columns([3, 2])
    with r1c1:
        name = st.text_input("Restaurant Name", placeholder="e.g. Le Bernardin", key="f_name")
    with r1c2:
        platform = st.selectbox("Platform", ["resy", "opentable"], key="f_platform")

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        label = "Resy Venue ID" if platform == "resy" else "OpenTable RID"
        vid = st.text_input(label, placeholder="e.g. 1234", key="f_vid")
    with r2c2:
        party = st.number_input("Party Size", min_value=1, max_value=20, value=2, key="f_party")

    r3c1, r3c2, r3c3 = st.columns(3)
    with r3c1:
        res_date = st.date_input("Date", value=date.today() + timedelta(days=7), key="f_date")
    with r3c2:
        earliest = st.text_input("Earliest Time (HH:MM)", value="18:00", key="f_earliest")
    with r3c3:
        latest = st.text_input("Latest Time (HH:MM)", value="22:00", key="f_latest")

    st.markdown('<div style="height:0.2rem"></div>', unsafe_allow_html=True)

    if st.button("＋  Add to Watch List", key="btn_add", type="primary", use_container_width=True):
        err = ""
        if not name.strip():
            err = "Please enter a restaurant name."
        elif not vid.strip() or not vid.strip().isdigit():
            err = "Venue ID must be a number."
        elif earliest > latest:
            err = "Earliest time must be before latest time."
        if err:
            st.error(err)
        else:
            entry = {
                "id":         st.session_state.next_id,
                "name":       name.strip(),
                "platform":   platform,
                "venue_id":   int(vid) if platform == "resy" else None,
                "rid":        int(vid) if platform == "opentable" else None,
                "date":       res_date.strftime("%Y-%m-%d"),
                "earliest":   earliest,
                "latest":     latest,
                "party_size": int(party),
            }
            st.session_state.queue.append(entry)
            st.session_state.next_id += 1
            st.success(f"✓  {name} added to watch list.")
            st.experimental_rerun()


# ── Render: queue (pre-monitoring) ────────────────────────────────────────────
def render_queue():
    if not st.session_state.queue:
        st.markdown(
            '<p style="color:#30305a;font-size:0.82rem;font-style:italic;'
            'padding:0.6rem 0;">No restaurants added yet.</p>',
            unsafe_allow_html=True,
        )
        return

    st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)
    _section("Watch List", "◎")

    for r in list(st.session_state.queue):
        pid   = r["venue_id"] if r["platform"] == "resy" else r["rid"]
        color = "#a78bfa" if r["platform"] == "resy" else "#38bdf8"
        badge = _badge(r["platform"], color + "22", color)

        col_info, col_btn = st.columns([8, 1])
        with col_info:
            st.markdown(
                f'<div style="padding:0.5rem 0;border-bottom:1px solid #0e0e22;">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px;">'
                f'<span style="color:#ddddf0;font-weight:600;font-size:0.88rem;">{r["name"]}</span>'
                f'{badge}</div>'
                f'<span style="color:#383870;font-size:0.76rem;">'
                f'ID&nbsp;{pid}&ensp;·&ensp;{r["date"]}&ensp;·&ensp;'
                f'{r["earliest"]}–{r["latest"]}&ensp;·&ensp;party&nbsp;of&nbsp;{r["party_size"]}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("✕", key=f"rm_{r['id']}"):
                st.session_state.queue = [x for x in st.session_state.queue if x["id"] != r["id"]]
                st.experimental_rerun()


# ── Render: settings + start/stop ─────────────────────────────────────────────
def render_settings_and_controls():
    _section("Settings", "⚙")

    phone = st.text_input(
        "Your 10-Digit Phone Number",
        placeholder="2125551234  →  sends to 2125551234@tmomail.net",
        max_chars=10,
        key="s_phone",
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        freq = st.number_input("Check Every (minutes)", min_value=1, max_value=120, value=5, key="s_freq")
    with sc2:
        stop_date = st.date_input(
            "Stop Monitoring After",
            value=date.today() + timedelta(days=7),
            key="s_stop",
        )

    st.markdown('<div style="height:0.8rem"></div>', unsafe_allow_html=True)

    if not _ms["active"]:
        if st.button("▶  Start Monitoring", key="btn_start", type="primary", use_container_width=True):
            phone_val = (phone or "").strip()
            if not st.session_state.queue:
                st.error("Add at least one restaurant first.")
            elif len(phone_val) != 10 or not phone_val.isdigit():
                st.error("Enter a valid 10-digit phone number (digits only).")
            elif not GMAIL_FROM or not GMAIL_PASSWORD:
                st.error("Gmail credentials not set — fill in config.py first.")
            else:
                sms_to = f"{phone_val}@tmomail.net"
                _start(st.session_state.queue, int(freq) * 60, stop_date, sms_to)
                st.session_state.queue = []
                st.experimental_rerun()
    else:
        if st.button("⏹  Stop All Monitoring", key="btn_stop", use_container_width=True):
            _stop_all()
            st.experimental_rerun()

        st.markdown(
            '<p style="color:#383870;font-size:0.76rem;text-align:center;margin-top:0.4rem;">'
            'Monitoring is live. Type restaurant ID to stop individually in the status panel below.'
            '</p>',
            unsafe_allow_html=True,
        )


# ── Render: live status ────────────────────────────────────────────────────────
def render_status():
    with _lock:
        restaurants = list(_ms["restaurants"])
        found       = dict(_ms["found"])
        active      = _ms["active"]

    if not active and not restaurants and not found:
        return

    st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    _section("Live Status", "●")

    # ── "found" reservation banners ───────────────────────────────────────────
    for rid, info in list(found.items()):
        r     = info["restaurant"]
        slots = info["slots"]
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#052014,#041c1c);'
            f'border:1px solid #16532d;border-radius:12px;'
            f'padding:1rem 1.2rem;margin-bottom:0.8rem;">'
            f'<div style="font-size:1.1rem;font-weight:700;color:#4ade80;margin-bottom:4px;">'
            f'🎉  Reservation Found!</div>'
            f'<div style="color:#86efac;font-size:0.88rem;margin-bottom:4px;">'
            f'{r["name"]} &nbsp;·&nbsp; {", ".join(slots)} &nbsp;·&nbsp; '
            f'{r["date"]} &nbsp;·&nbsp; party of {r["party_size"]}</div>'
            f'<div style="color:#4a7060;font-size:0.78rem;">'
            f'SMS already sent. Stop watching this restaurant?</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        fc1, fc2, _ = st.columns([2, 2, 4])
        with fc1:
            if st.button("✓  Yes, stop watching", key=f"yes_{rid}", type="primary"):
                _remove(rid, r["name"])
                st.experimental_rerun()
        with fc2:
            if st.button("↺  Keep monitoring", key=f"no_{rid}"):
                with _lock:
                    _ms["found"].pop(rid, None)
                st.experimental_rerun()

    # ── Restaurant status cards ───────────────────────────────────────────────
    if restaurants:
        num_cols = min(len(restaurants), 3)
        cols     = st.columns(num_cols)
        for i, r in enumerate(restaurants):
            pid       = r["venue_id"] if r["platform"] == "resy" else r["rid"]
            is_found  = r["id"] in found
            dot_color = "#facc15" if is_found else "#4ade80"
            dot_label = "Slot found" if is_found else "Watching"
            plat_col  = "#a78bfa" if r["platform"] == "resy" else "#38bdf8"
            badge     = _badge(r["platform"], plat_col + "22", plat_col)

            with cols[i % num_cols]:
                st.markdown(
                    f'<div style="background:#0b0b1e;border:1px solid #1a1a30;'
                    f'border-radius:13px;padding:1rem 1.1rem 0.5rem;">'
                    # header row
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:flex-start;margin-bottom:6px;">'
                    f'<span style="color:#ddddf0;font-weight:600;font-size:0.9rem;'
                    f'line-height:1.3;">{r["name"]}</span>'
                    f'<span style="display:flex;align-items:center;gap:5px;white-space:nowrap;">'
                    f'<span style="width:7px;height:7px;background:{dot_color};border-radius:50%;'
                    f'display:inline-block;box-shadow:0 0 7px {dot_color}88;"></span>'
                    f'<span style="color:{dot_color};font-size:0.68rem;font-weight:700;">'
                    f'{dot_label}</span></span></div>'
                    # badges + meta
                    f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;">'
                    f'{badge}'
                    f'<span style="color:#383870;font-size:0.72rem;">ID&nbsp;{pid}</span></div>'
                    f'<div style="color:#383870;font-size:0.73rem;line-height:1.6;">'
                    f'{r["date"]}&ensp;·&ensp;{r["earliest"]}–{r["latest"]}'
                    f'&ensp;·&ensp;party&nbsp;{r["party_size"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Stop", key=f"stop_{r['id']}", help=f"Stop watching {r['name']}"):
                    _remove(r["id"], r["name"])
                    st.experimental_rerun()
                st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)


# ── Render: activity log ──────────────────────────────────────────────────────
def render_log():
    with _lock:
        log_entries = list(reversed(_ms["log"][-60:]))

    if not log_entries:
        return

    st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)

    with st.expander("Activity Log"):
        level_styles = {
            "FOUND": ("color:#4ade80;font-weight:700;", "color:#86efac;"),
            "INFO":  ("color:#404880;font-weight:500;", "color:#6060a0;"),
            "WARN":  ("color:#fbbf24;font-weight:700;", "color:#fde68a;"),
            "ERROR": ("color:#f87171;font-weight:700;", "color:#fca5a5;"),
        }
        rows = []
        for e in log_entries:
            ls, ms = level_styles.get(e["level"], level_styles["INFO"])
            rows.append(
                f'<div style="display:flex;gap:10px;padding:4px 0;'
                f'border-bottom:1px solid #0d0d1e;align-items:baseline;">'
                f'<span style="color:#252545;font-size:0.72rem;'
                f'min-width:52px;font-family:monospace;">{e["ts"]}</span>'
                f'<span style="{ls}font-size:0.7rem;min-width:44px;">{e["level"]}</span>'
                f'<span style="{ms}font-size:0.78rem;">{e["msg"]}</span>'
                f'</div>'
            )
        st.markdown(
            '<div style="background:#060610;border-radius:8px;padding:0.6rem 0.8rem;'
            'max-height:280px;overflow-y:auto;font-family:monospace;">'
            + "".join(rows) +
            '</div>',
            unsafe_allow_html=True,
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    render_header()
    render_add_form()
    st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)
    render_queue()
    st.markdown("<hr>", unsafe_allow_html=True)
    render_settings_and_controls()
    render_status()
    render_log()

    # Auto-refresh every 4 seconds while monitoring is active so status stays live.
    # (Works by sleeping briefly then triggering a Streamlit rerun.)
    if _ms["active"]:
        time.sleep(4)
        st.experimental_rerun()


main()
