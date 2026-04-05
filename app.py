#!/usr/bin/env python3
"""
app.py — Streamlit frontend for the Restaurant Reservation Monitor.

Run with:
    conda activate resmon
    streamlit run app.py
"""

import smtplib
import threading
import sys
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as _components

# ── project imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from monitor import check_resy, check_opentable, lookup_resy_venue

# On Streamlit Cloud, credentials live in the secrets dashboard.
# Locally, they live in config.py (gitignored).
try:
    GMAIL_FROM     = st.secrets["GMAIL_FROM"]
    GMAIL_PASSWORD = st.secrets["GMAIL_PASSWORD"]
except (KeyError, FileNotFoundError):
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
.stApp { background: #07070f !important; font-family: 'Inter', system-ui, sans-serif !important; }
[data-testid="stAppViewContainer"] { background: #07070f !important; }
[data-testid="stHeader"]  { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
.block-container { padding: 2rem 3rem 4rem !important; max-width: 1320px !important; }

/* ── Widget labels ── */
[data-testid="stWidgetLabel"] p {
    color: #5858a0 !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
}

/* ── Text / number inputs ── */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
    background: #0e0e26 !important;
    border: 1.5px solid #1c1c3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.9rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-baseweb="input"] input:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.13) !important;
    outline: none !important;
}

/* ── Select ── */
[data-baseweb="select"] > div {
    background: #0e0e26 !important;
    border: 1.5px solid #1c1c3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
}
[data-baseweb="popover"] { background: #131330 !important; border: 1px solid #22224a !important; }
[data-baseweb="menu"]    { background: #131330 !important; }
[data-baseweb="option"]:hover { background: #1e1e44 !important; }

/* ── Date input ── */
[data-testid="stDateInput"] input {
    background: #0e0e26 !important;
    border: 1.5px solid #1c1c3a !important;
    border-radius: 9px !important;
    color: #ddddf0 !important;
}

/* ── Number input stepper buttons ── */
[data-testid="stNumberInput"] button {
    background: #0e0e26 !important;
    border-color: #1c1c3a !important;
    color: #6060a0 !important;
}

/* ── Bordered containers (cards) ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #0b0b1e !important;
    border: 1px solid #18183a !important;
    border-radius: 16px !important;
    padding: 0.2rem !important;
}

/* ── Primary buttons ── */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #7c3aed 0%, #4338ca 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 2px 16px rgba(124,58,237,0.35) !important;
    transition: all 0.18s ease !important;
}
[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #8b4cf6 0%, #5046e5 100%) !important;
    box-shadow: 0 5px 24px rgba(124,58,237,0.55) !important;
    transform: translateY(-1px) !important;
}

/* ── Secondary buttons ── */
[data-testid="baseButton-secondary"] {
    background: #0c0c22 !important;
    border: 1.5px solid #1c1c38 !important;
    border-radius: 10px !important;
    color: #7070a8 !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    transition: all 0.18s ease !important;
}
[data-testid="baseButton-secondary"]:hover {
    border-color: #7c3aed !important;
    color: #c4b5fd !important;
    background: #110c26 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #0b0b1e !important;
    border: 1px solid #18183a !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary {
    color: #5858a0 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
}

/* ── Divider ── */
hr { border-color: #12122a !important; margin: 1.4rem 0 !important; }

/* ── Alert boxes ── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #07070f; }
::-webkit-scrollbar-thumb { background: #1c1c38; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ── Module-level monitoring state ─────────────────────────────────────────────
# Shared between Streamlit reruns and the background monitor thread.
_lock = threading.Lock()
_ms: dict = {
    "active":      False,
    "stop_event":  threading.Event(),
    "restaurants": [],   # live watch list; thread reads/UI modifies
    "log":         [],   # [{"ts", "level", "msg"}, ...]
    "alerted":     set(),
    "found":       {},   # restaurant id → {"restaurant": ..., "slots": [...]}
    "last_check":  None, # datetime of last completed check cycle
}
_MAX_LOG = 300


def _log(level: str, msg: str) -> None:
    with _lock:
        _ms["log"].append({"ts": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg})
        if len(_ms["log"]) > _MAX_LOG:
            _ms["log"] = _ms["log"][-_MAX_LOG:]


# ── SMS ───────────────────────────────────────────────────────────────────────
def _send_sms(restaurant: dict, slots: list, sms_to: str) -> None:
    if not GMAIL_FROM or not GMAIL_PASSWORD:
        _log("WARN", "Gmail credentials missing — SMS skipped.")
        return
    body = (
        f"{restaurant['name']} ({restaurant['platform']}) has openings on "
        f"{restaurant['date']}: {', '.join(slots)} for {restaurant['party_size']}. Book now!"
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
def _monitor_loop(interval: int, stop_date: date, sms_to: str) -> None:
    _log("INFO", f"Monitor started — checking every {interval}s until {stop_date}.")
    while not _ms["stop_event"].is_set():
        if date.today() > stop_date:
            _log("INFO", "Stop date reached — monitoring ended.")
            break

        with _lock:
            current = list(_ms["restaurants"])
        if not current:
            _log("INFO", "No restaurants left — monitoring ended.")
            break

        for r in current:
            rid = r["id"]
            if rid in _ms["found"]:
                continue
            try:
                slots = check_resy(r) if r["platform"] == "resy" else check_opentable(r)
            except Exception as exc:
                _log("ERROR", f"[{rid}] {r['name']}: {exc}")
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
                _log("INFO", f"[{rid}] {r['name']} — available (already alerted)")

        # Record time of last completed cycle
        with _lock:
            _ms["last_check"] = datetime.now()

        _ms["stop_event"].wait(interval)

    _ms["active"] = False
    _log("INFO", "Monitor stopped.")


def _start(restaurants: list, interval: int, stop_date: date, sms_to: str) -> None:
    _ms["stop_event"].clear()
    with _lock:
        _ms["restaurants"] = list(restaurants)
        _ms["log"]         = []
        _ms["alerted"]     = set()
        _ms["found"]       = {}
        _ms["last_check"]  = None
    _ms["active"] = True
    threading.Thread(
        target=_monitor_loop,
        args=(interval, stop_date, sms_to),
        daemon=True,
    ).start()


def _stop_all() -> None:
    _ms["stop_event"].set()
    _ms["active"] = False
    with _lock:
        _ms["restaurants"] = []
    _log("INFO", "Monitoring stopped by user.")


def _remove(rid: int, name: str) -> None:
    with _lock:
        _ms["restaurants"] = [r for r in _ms["restaurants"] if r["id"] != rid]
        _ms["found"].pop(rid, None)
    _log("INFO", f"[{rid}] {name} removed from watch list.")


# ── Session state init ────────────────────────────────────────────────────────
if "pending" not in st.session_state:
    st.session_state.pending = []   # restaurants queued before Start is clicked
    st.session_state.next_id = 1


# ── UI helpers ────────────────────────────────────────────────────────────────
def _label(text: str) -> None:
    st.markdown(
        f'<p style="color:#5050a0;font-size:0.68rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.12em;margin:0 0 0.6rem;">{text}</p>',
        unsafe_allow_html=True,
    )


def _badge(text: str, fg: str) -> str:
    return (
        f'<span style="background:{fg}22;color:{fg};padding:2px 9px;border-radius:999px;'
        f'font-size:0.7rem;font-weight:700;letter-spacing:0.04em;">{text}</span>'
    )


def _dot(color: str, label: str) -> str:
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;">'
        f'<span style="width:7px;height:7px;background:{color};border-radius:50%;'
        f'box-shadow:0 0 7px {color}99;"></span>'
        f'<span style="color:{color};font-size:0.68rem;font-weight:700;">{label}</span>'
        f'</span>'
    )


# ── Header ────────────────────────────────────────────────────────────────────
def render_header() -> None:
    active = _ms["active"]
    with _lock:
        last_check = _ms["last_check"]

    if active:
        last_str = last_check.strftime("%-I:%M:%S %p") if last_check else "checking…"
        status_html = (
            '<span style="display:inline-flex;align-items:center;gap:8px;">'
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'background:#0d2e1a;border:1px solid #16532d;border-radius:999px;padding:4px 12px;">'
            '<span style="width:8px;height:8px;background:#4ade80;border-radius:50%;'
            'box-shadow:0 0 8px #4ade8099;animation:pulse 1.5s infinite;"></span>'
            '<span style="color:#4ade80;font-size:0.75rem;font-weight:700;">MONITORING ACTIVE</span>'
            '</span>'
            f'<span style="color:#2a2a4a;font-size:0.72rem;">last checked {last_str}</span>'
            '</span>'
            '<style>@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}</style>'
        )
    else:
        status_html = ""

    st.markdown(f"""
    <div style="padding:2.2rem 0 1.6rem;border-bottom:1px solid #111128;margin-bottom:2rem;">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
        <div style="display:flex;align-items:center;gap:16px;">
          <div style="width:50px;height:50px;flex-shrink:0;
                      background:linear-gradient(135deg,#7c3aed,#4338ca);
                      border-radius:14px;display:flex;align-items:center;
                      justify-content:center;font-size:1.5rem;
                      box-shadow:0 4px 22px rgba(124,58,237,0.45);">🍽️</div>
          <div>
            <h1 style="margin:0;font-size:1.9rem;font-weight:700;line-height:1.15;
                       background:linear-gradient(125deg,#a78bfa 20%,#60a5fa 100%);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
              Reservation Monitor
            </h1>
            <p style="margin:0;color:#3a3a6a;font-size:0.82rem;">
              Resy &amp; OpenTable &nbsp;·&nbsp; NYC &nbsp;·&nbsp; SMS alerts
            </p>
          </div>
        </div>
        <div>{status_html}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Add-restaurant form ───────────────────────────────────────────────────────
def render_add_form() -> None:
    active = _ms["active"]

    with st.container(border=True):
        _label("＋  Add Restaurant")

        platform = st.selectbox("Platform", ["resy", "opentable"], key="f_platform")

        venue_id      = None
        resolved_name = ""

        if platform == "resy":
            st.markdown(
                '<p style="color:#36367a;font-size:0.78rem;margin:0.2rem 0 0.4rem;">'
                'Paste the Resy URL from your browser for the restaurant you want to monitor.</p>',
                unsafe_allow_html=True,
            )
            resy_url = st.text_input(
                "Resy URL",
                placeholder="https://resy.com/cities/new-york-ny/venues/lilia",
                key="f_resy_url",
            )
            if resy_url and "/venues/" in resy_url:
                with st.spinner("Looking up venue…"):
                    info = lookup_resy_venue(resy_url)
                if info:
                    venue_id      = info["venue_id"]
                    resolved_name = info["name"]
                    meta = " · ".join(filter(None, [info.get("neighborhood", ""), info.get("cuisine", "")]))
                    st.markdown(
                        f'<div style="background:#0d0d28;border:1px solid #22224a;border-radius:10px;'
                        f'padding:0.65rem 1rem;margin:0.3rem 0 0.5rem;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                        f'<span style="color:#ddddf0;font-weight:600;font-size:0.9rem;">{info["name"]}</span>'
                        f'<span style="background:#a78bfa22;color:#a78bfa;padding:2px 10px;'
                        f'border-radius:999px;font-size:0.72rem;font-weight:700;">'
                        f'Resy ID&nbsp;{venue_id}</span>'
                        f'</div>'
                        f'<span style="color:#36367a;font-size:0.76rem;">{meta}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("Couldn't resolve that URL — check it's a valid Resy restaurant page.")
        else:
            st.markdown(
                '<p style="color:#36367a;font-size:0.78rem;margin:0.2rem 0 0.4rem;">'
                'Go to <a href="https://www.opentable.com" target="_blank" '
                'style="color:#38bdf8;text-decoration:none;">opentable.com</a>, open the restaurant '
                'page, and copy the <code style="color:#38bdf8;background:#0a1a26;padding:1px 5px;'
                'border-radius:4px;">rid=XXXXX</code> from the URL.</p>',
                unsafe_allow_html=True,
            )
            resolved_name = st.text_input("Restaurant Name", placeholder="e.g. Carbone", key="f_ot_name")
            venue_id = st.number_input("OpenTable rid", min_value=1, value=1, step=1, key="f_ot_id")

        c1, c2, c3 = st.columns(3)
        with c1:
            res_date = st.date_input("Date", value=date.today() + timedelta(days=1), key="f_date")
        with c2:
            earliest = st.text_input("Earliest", value="18:00", key="f_earliest")
        with c3:
            latest = st.text_input("Latest", value="22:00", key="f_latest")

        party = st.number_input("Party Size", min_value=1, max_value=20, value=2, key="f_party")

        if st.button("＋  Add", key="btn_add", use_container_width=True):
            if platform == "resy" and not venue_id:
                st.error("Paste a valid Resy URL first.")
            elif platform == "opentable" and not resolved_name.strip():
                st.error("Enter the restaurant name.")
            elif earliest >= latest:
                st.error("Earliest must be before latest.")
            else:
                entry = {
                    "id":         st.session_state.next_id,
                    "name":       resolved_name.strip() if resolved_name else "",
                    "platform":   platform,
                    "venue_id":   int(venue_id) if platform == "resy" else None,
                    "rid":        int(venue_id) if platform == "opentable" else None,
                    "date":       res_date.strftime("%Y-%m-%d"),
                    "earliest":   earliest,
                    "latest":     latest,
                    "party_size": int(party),
                }
                if active:
                    # Monitoring already running — inject directly into live list
                    with _lock:
                        _ms["restaurants"].append(entry)
                    _log("INFO", f"[{entry['id']}] {entry['name']} added to active watch list.")
                else:
                    st.session_state.pending.append(entry)
                st.session_state.next_id += 1
                st.rerun()


# ── Pending list ──────────────────────────────────────────────────────────────
def render_pending() -> None:
    pending = st.session_state.pending
    active  = _ms["active"]

    # While monitoring is active show the live list instead
    if active:
        with _lock:
            live = list(_ms["restaurants"])
        if not live:
            return
        with st.container(border=True):
            _label("◎  Watching")
            for r in live:
                pid   = r["venue_id"] if r["platform"] == "resy" else r["rid"]
                color = "#a78bfa" if r["platform"] == "resy" else "#38bdf8"
                ci, cb = st.columns([9, 1])
                with ci:
                    st.markdown(
                        f'<div style="padding:0.35rem 0;border-bottom:1px solid #0e0e22;">'
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:1px;">'
                        f'<span style="color:#ddddf0;font-weight:600;font-size:0.87rem;">{r["name"]}</span>'
                        f'{_badge(r["platform"], color)}</div>'
                        f'<span style="color:#2a2a52;font-size:0.74rem;">'
                        f'{r["date"]} · {r["earliest"]}–{r["latest"]} · party&nbsp;{r["party_size"]}'
                        f'</span></div>',
                        unsafe_allow_html=True,
                    )
                with cb:
                    if st.button("✕", key=f"lrm_{r['id']}"):
                        _remove(r["id"], r["name"])
                        st.rerun()
        return

    if not pending:
        st.markdown(
            '<p style="color:#22224a;font-size:0.82rem;font-style:italic;padding:0.3rem 0;">'
            'No restaurants added yet.</p>',
            unsafe_allow_html=True,
        )
        return

    with st.container(border=True):
        _label("◎  Ready to Monitor")
        for r in list(pending):
            pid   = r["venue_id"] if r["platform"] == "resy" else r["rid"]
            color = "#a78bfa" if r["platform"] == "resy" else "#38bdf8"
            ci, cb = st.columns([9, 1])
            with ci:
                st.markdown(
                    f'<div style="padding:0.35rem 0;border-bottom:1px solid #0e0e22;">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:1px;">'
                    f'<span style="color:#ddddf0;font-weight:600;font-size:0.87rem;">{r["name"]}</span>'
                    f'{_badge(r["platform"], color)}</div>'
                    f'<span style="color:#2a2a52;font-size:0.74rem;">'
                    f'{r["date"]} · {r["earliest"]}–{r["latest"]} · party&nbsp;{r["party_size"]}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
            with cb:
                if st.button("✕", key=f"rm_{r['id']}"):
                    st.session_state.pending = [x for x in pending if x["id"] != r["id"]]
                    st.rerun()


# ── Controls (right panel) ────────────────────────────────────────────────────
def render_controls() -> None:
    active = _ms["active"]

    with st.container(border=True):
        _label("⚙  Settings")
        phone = st.text_input(
            "10-Digit Phone Number",
            placeholder="2125551234  →  SMS via T-Mobile gateway",
            max_chars=10,
            key="s_phone",
        )
        c1, c2 = st.columns(2)
        with c1:
            freq = st.number_input("Check Every (min)", min_value=1, max_value=120, value=5, key="s_freq")
        with c2:
            stop_date = st.date_input(
                "Auto-stop After",
                value=date.today() + timedelta(days=7),
                key="s_stop",
            )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    if not active:
        # Green "Start Monitoring" button via JS colour injection
        _components.html("""<script>
            (function paint() {
                const btns = window.parent.document.querySelectorAll(
                    '[data-testid="baseButton-primary"]');
                let found = false;
                btns.forEach(b => {
                    if (b.innerText.includes('Start Monitoring')) {
                        b.style.setProperty('background',
                            'linear-gradient(135deg,#16a34a,#15803d)', 'important');
                        b.style.setProperty('box-shadow',
                            '0 2px 16px rgba(22,163,74,0.4)', 'important');
                        found = true;
                    }
                });
                if (!found) setTimeout(paint, 80);
            })();
        </script>""", height=0)

        if st.button("▶  Start Monitoring", key="btn_start", type="primary", use_container_width=True):
            phone_val = (phone or "").strip()
            if not st.session_state.pending:
                st.error("Add at least one restaurant first.")
            elif len(phone_val) != 10 or not phone_val.isdigit():
                st.error("Enter a valid 10-digit phone number.")
            elif not GMAIL_FROM or not GMAIL_PASSWORD:
                st.error("Gmail credentials not configured (config.py).")
            else:
                _start(
                    st.session_state.pending,
                    int(freq) * 60,
                    stop_date,
                    f"{phone_val}@tmomail.net",
                )
                st.session_state.pending = []
                st.rerun()
    else:
        # Active: show green status banner + stop button
        with _lock:
            last_check = _ms["last_check"]
            n_watching = len(_ms["restaurants"])

        last_str = last_check.strftime("%-I:%M:%S %p") if last_check else "first check in progress…"
        st.markdown(
            f'<div style="background:#071a0f;border:1px solid #15532a;border-radius:12px;'
            f'padding:0.9rem 1.1rem;margin-bottom:0.6rem;">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
            f'<span style="width:9px;height:9px;background:#4ade80;border-radius:50%;'
            f'box-shadow:0 0 8px #4ade80cc;flex-shrink:0;"></span>'
            f'<span style="color:#4ade80;font-weight:700;font-size:0.9rem;">Monitoring Active</span>'
            f'</div>'
            f'<span style="color:#1e5c36;font-size:0.78rem;">'
            f'Watching {n_watching} restaurant{"s" if n_watching != 1 else ""}'
            f' &nbsp;·&nbsp; last checked {last_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("⏹  Stop Monitoring", key="btn_stop", use_container_width=True):
            _stop_all()
            st.rerun()


# ── Found-reservation banners (auto-refresh) ──────────────────────────────────
@st.fragment(run_every=5)
def render_found() -> None:
    with _lock:
        found  = dict(_ms["found"])
        active = _ms["active"]
    if not found:
        return
    for rid, info in list(found.items()):
        r, slots = info["restaurant"], info["slots"]
        with st.container(border=True):
            st.markdown(
                f'<div style="background:linear-gradient(135deg,#052014,#041c1c);'
                f'border-radius:10px;padding:0.9rem 1rem;margin-bottom:0.4rem;">'
                f'<div style="font-size:1.05rem;font-weight:700;color:#4ade80;margin-bottom:4px;">'
                f'🎉  Reservation Found!</div>'
                f'<div style="color:#86efac;font-size:0.87rem;margin-bottom:4px;">'
                f'{r["name"]} · {", ".join(slots)} · {r["date"]} · party of {r["party_size"]}</div>'
                f'<div style="color:#3a6050;font-size:0.77rem;">SMS sent. Stop watching this restaurant?</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            bc1, bc2, _ = st.columns([2, 2, 4])
            with bc1:
                if st.button("✓  Yes, stop", key=f"yes_{rid}", type="primary"):
                    _remove(rid, r["name"])
                    st.rerun()
            with bc2:
                if st.button("↺  Keep watching", key=f"no_{rid}"):
                    with _lock:
                        _ms["found"].pop(rid, None)
                    st.rerun()


# ── Activity log (auto-refresh) ───────────────────────────────────────────────
@st.fragment(run_every=5)
def render_log() -> None:
    with _lock:
        entries    = list(reversed(_ms["log"][-60:]))
        active     = _ms["active"]
        last_check = _ms["last_check"]

    if not entries:
        return

    level_style = {
        "FOUND": ("#4ade80", "#86efac"),
        "INFO":  ("#363680", "#5858a0"),
        "WARN":  ("#fbbf24", "#fde68a"),
        "ERROR": ("#f87171", "#fca5a5"),
    }
    with st.expander("Activity Log", expanded=active):
        rows = []
        for e in entries:
            lc, mc = level_style.get(e["level"], level_style["INFO"])
            rows.append(
                f'<div style="display:flex;gap:10px;padding:4px 0;border-bottom:1px solid #0d0d1e;">'
                f'<span style="color:#222242;font-size:0.72rem;min-width:52px;font-family:monospace;">'
                f'{e["ts"]}</span>'
                f'<span style="color:{lc};font-size:0.7rem;font-weight:700;min-width:44px;">'
                f'{e["level"]}</span>'
                f'<span style="color:{mc};font-size:0.78rem;">{e["msg"]}</span>'
                f'</div>'
            )
        st.markdown(
            '<div style="background:#060610;border-radius:8px;padding:0.6rem 0.8rem;'
            'max-height:320px;overflow-y:auto;font-family:monospace;">'
            + "".join(rows) + '</div>',
            unsafe_allow_html=True,
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    render_header()

    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        render_add_form()
        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        render_pending()
    with right:
        render_controls()

    render_found()
    render_log()


main()
