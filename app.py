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

sys.path.insert(0, str(Path(__file__).parent))
from monitor import check_resy, check_opentable, lookup_resy_venue

try:
    GMAIL_FROM     = st.secrets["GMAIL_FROM"]
    GMAIL_PASSWORD = st.secrets["GMAIL_PASSWORD"]
except (KeyError, FileNotFoundError):
    try:
        from config import GMAIL_FROM, GMAIL_PASSWORD
    except ImportError:
        GMAIL_FROM = GMAIL_PASSWORD = ""

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reservation Monitor",
    page_icon="🍽️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Base ── */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: #06080f !important;
    font-family: 'Inter', system-ui, sans-serif !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
.block-container {
    padding: 2.5rem 1.5rem 5rem !important;
    max-width: 700px !important;
}

/* ── Section labels ── */
.sec-label {
    color: #1e4a8a;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 0 0 0.7rem;
}

/* ── Widget labels ── */
[data-testid="stWidgetLabel"] p {
    color: #2a4070 !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}

/* ── Text / number inputs ── */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background: #080e1f !important;
    border: 1.5px solid #111e3c !important;
    border-radius: 9px !important;
    color: #c8d8f0 !important;
    font-size: 0.9rem !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
}
[data-baseweb="input"] input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.15) !important;
    outline: none !important;
}

/* ── Select ── */
[data-baseweb="select"] > div {
    background: #080e1f !important;
    border: 1.5px solid #111e3c !important;
    border-radius: 9px !important;
    color: #c8d8f0 !important;
}
[data-baseweb="popover"] { background: #0c1428 !important; border: 1px solid #1a2d50 !important; }
[data-baseweb="menu"]    { background: #0c1428 !important; }
[data-baseweb="option"]:hover { background: #101d38 !important; }

/* ── Date input ── */
[data-testid="stDateInput"] input {
    background: #080e1f !important;
    border: 1.5px solid #111e3c !important;
    border-radius: 9px !important;
    color: #c8d8f0 !important;
}

/* ── Number input steppers ── */
[data-testid="stNumberInput"] button {
    background: #080e1f !important;
    border-color: #111e3c !important;
    color: #2a4070 !important;
}

/* ── Bordered containers ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #080c1a !important;
    border: 1px solid #0f1b34 !important;
    border-radius: 14px !important;
    padding: 0.2rem !important;
}

/* ── Primary buttons (blue gradient) ── */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #1d4ed8 0%, #0891b2 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    box-shadow: 0 2px 18px rgba(37,99,235,0.35) !important;
    transition: all 0.18s ease !important;
}
[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%) !important;
    box-shadow: 0 4px 26px rgba(37,99,235,0.55) !important;
    transform: translateY(-1px) !important;
}

/* ── Secondary buttons ── */
[data-testid="baseButton-secondary"] {
    background: #080c1a !important;
    border: 1.5px solid #111e3c !important;
    border-radius: 10px !important;
    color: #2a4880 !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    transition: all 0.18s ease !important;
}
[data-testid="baseButton-secondary"]:hover {
    border-color: #2563eb !important;
    color: #7eb8f0 !important;
    background: #090f22 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #080c1a !important;
    border: 1px solid #0f1b34 !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary {
    color: #1e3a60 !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}

/* ── Alerts ── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Divider ── */
hr { border-color: #0c1428 !important; margin: 1.6rem 0 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #06080f; }
::-webkit-scrollbar-thumb { background: #111e3c; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2563eb; }
</style>
""", unsafe_allow_html=True)

# ── Module-level monitoring state ─────────────────────────────────────────────
_lock = threading.Lock()
_ms: dict = {
    "active":      False,
    "stop_event":  threading.Event(),
    "restaurants": [],
    "log":         [],
    "alerted":     set(),
    "found":       {},
    "last_check":  None,
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
    _log("INFO", f"Monitor started — every {interval}s until {stop_date}.")
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
    threading.Thread(target=_monitor_loop, args=(interval, stop_date, sms_to), daemon=True).start()


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
    _log("INFO", f"[{rid}] {name} removed.")


# ── Session state ─────────────────────────────────────────────────────────────
if "pending" not in st.session_state:
    st.session_state.pending  = []
    st.session_state.next_id  = 1
    st.session_state.form_gen = 0   # bump to reset all form widgets


# ── HTML helpers ──────────────────────────────────────────────────────────────
def _h(text: str) -> None:
    """Section header label."""
    st.markdown(f'<p class="sec-label">{text}</p>', unsafe_allow_html=True)


def _badge(text: str, color: str = "#3b82f6") -> str:
    return (
        f'<span style="background:{color}1a;color:{color};padding:2px 10px;'
        f'border-radius:999px;font-size:0.68rem;font-weight:700;">{text}</span>'
    )


def _dot(color: str, label: str) -> str:
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;">'
        f'<span style="width:7px;height:7px;background:{color};border-radius:50%;'
        f'box-shadow:0 0 6px {color}99;"></span>'
        f'<span style="color:{color};font-size:0.68rem;font-weight:700;">{label}</span>'
        f'</span>'
    )


# ── Header ────────────────────────────────────────────────────────────────────
def render_header() -> None:
    active = _ms["active"]
    with _lock:
        last_check = _ms["last_check"]

    last_str = ""
    if active and last_check:
        last_str = f'last checked {last_check.strftime("%-I:%M:%S %p")}'
    elif active:
        last_str = "first check in progress…"

    status_dot = ""
    if active:
        status_dot = (
            '<span style="display:inline-flex;align-items:center;gap:7px;'
            'background:#071426;border:1px solid #0f2d52;border-radius:999px;padding:5px 14px;">'
            '<span style="width:8px;height:8px;background:#22d3ee;border-radius:50%;'
            'box-shadow:0 0 8px #22d3eeaa;"></span>'
            '<span style="color:#22d3ee;font-size:0.75rem;font-weight:700;letter-spacing:0.04em;">'
            'MONITORING ACTIVE</span>'
            '</span>'
        )

    st.markdown(f"""
    <div style="padding:2.5rem 0 1.8rem;border-bottom:1px solid #0c1428;margin-bottom:2.2rem;">
      <div style="display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div>
          <h1 style="margin:0 0 4px;font-size:1.8rem;font-weight:700;
                     background:linear-gradient(125deg,#60a5fa 10%,#22d3ee 90%);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                     line-height:1.15;">
            Reservation Monitor
          </h1>
          <p style="margin:0;color:#1e3a60;font-size:0.8rem;">
            Resy &amp; OpenTable &nbsp;·&nbsp; SMS alerts
          </p>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
          {status_dot}
          <span style="color:#122040;font-size:0.7rem;">{last_str}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Monitoring active view ────────────────────────────────────────────────────
@st.fragment(run_every=4)
def render_active_status() -> None:
    active = _ms["active"]
    if not active:
        return

    with _lock:
        restaurants = list(_ms["restaurants"])
        found       = dict(_ms["found"])
        last_check  = _ms["last_check"]

    n    = len(restaurants)
    last = last_check.strftime("%-I:%M:%S %p") if last_check else "checking…"

    # Green status banner
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#071a14,#06131e);'
        f'border:1px solid #0d3028;border-radius:14px;padding:1rem 1.2rem;margin-bottom:1rem;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">'
        f'<span style="width:9px;height:9px;background:#4ade80;border-radius:50%;'
        f'box-shadow:0 0 8px #4ade80cc;"></span>'
        f'<span style="color:#4ade80;font-weight:700;font-size:0.95rem;">Monitoring Active</span>'
        f'</div>'
        f'<span style="color:#1a5c40;font-size:0.78rem;">'
        f'Watching {n} restaurant{"s" if n!=1 else ""} &nbsp;·&nbsp; last checked {last}'
        f'</span>'
        f'</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # Found banners
    for rid, info in list(found.items()):
        r, slots = info["restaurant"], info["slots"]
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#04150e,#051218);'
            f'border:1px solid #0d3028;border-radius:12px;padding:0.9rem 1.1rem;margin-bottom:0.5rem;">'
            f'<div style="font-size:1rem;font-weight:700;color:#4ade80;margin-bottom:3px;">🎉 Reservation Found!</div>'
            f'<div style="color:#6ee7b7;font-size:0.85rem;margin-bottom:3px;">'
            f'{r["name"]} · {", ".join(slots)} · {r["date"]} · party of {r["party_size"]}'
            f'</div>'
            f'<div style="color:#1a5030;font-size:0.75rem;">SMS sent. Keep watching?</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c1, c2, _ = st.columns([2, 2, 4])
        with c1:
            if st.button("✓ Stop watching", key=f"yes_{rid}", type="primary"):
                _remove(rid, r["name"])
                st.rerun()
        with c2:
            if st.button("↺ Keep watching", key=f"no_{rid}"):
                with _lock:
                    _ms["found"].pop(rid, None)
                st.rerun()

    # Per-restaurant status cards
    if restaurants:
        cols = st.columns(min(len(restaurants), 3))
        for i, r in enumerate(restaurants):
            pid      = r["venue_id"] if r["platform"] == "resy" else r["rid"]
            is_found = r["id"] in found
            dc       = "#facc15" if is_found else "#4ade80"
            pc       = "#3b82f6" if r["platform"] == "resy" else "#22d3ee"
            with cols[i % len(cols)]:
                with st.container(border=True):
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                        f'<span style="color:#c8d8f0;font-weight:600;font-size:0.87rem;margin-bottom:4px;">'
                        f'{r["name"]}</span>'
                        f'{_dot(dc, "found" if is_found else "watching")}'
                        f'</div>'
                        f'<div style="display:flex;gap:5px;align-items:center;margin:3px 0;">'
                        f'{_badge(r["platform"], pc)}'
                        f'</div>'
                        f'<div style="color:#1a2e50;font-size:0.72rem;line-height:1.7;">'
                        f'{r["date"]} · {r["earliest"]}–{r["latest"]} · party {r["party_size"]}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Remove", key=f"stop_{r['id']}"):
                        _remove(r["id"], r["name"])
                        st.rerun()


# ── Activity log ──────────────────────────────────────────────────────────────
@st.fragment(run_every=4)
def render_log() -> None:
    with _lock:
        entries = list(reversed(_ms["log"][-80:]))
        active  = _ms["active"]
    if not entries:
        return

    colors = {
        "FOUND": ("#4ade80", "#6ee7b7"),
        "INFO":  ("#1e3a60", "#2a5080"),
        "WARN":  ("#fbbf24", "#fde68a"),
        "ERROR": ("#f87171", "#fca5a5"),
    }
    with st.expander("Activity Log", expanded=active):
        rows = []
        for e in entries:
            lc, mc = colors.get(e["level"], colors["INFO"])
            rows.append(
                f'<div style="display:flex;gap:10px;padding:4px 0;border-bottom:1px solid #090f1e;">'
                f'<span style="color:#111e36;font-size:0.7rem;min-width:50px;font-family:monospace;">'
                f'{e["ts"]}</span>'
                f'<span style="color:{lc};font-size:0.68rem;font-weight:700;min-width:42px;">'
                f'{e["level"]}</span>'
                f'<span style="color:{mc};font-size:0.76rem;">{e["msg"]}</span>'
                f'</div>'
            )
        st.markdown(
            '<div style="background:#040810;border-radius:8px;padding:0.6rem 0.8rem;'
            'max-height:300px;overflow-y:auto;font-family:monospace;">'
            + "".join(rows)
            + '</div>',
            unsafe_allow_html=True,
        )


# ── Add form ──────────────────────────────────────────────────────────────────
def render_form() -> None:
    g    = st.session_state.form_gen   # form generation — bump to reset widgets
    active = _ms["active"]

    st.markdown("<hr>", unsafe_allow_html=True)
    _h("Restaurant")

    platform = st.selectbox(
        "Platform",
        ["resy", "opentable"],
        key=f"f_platform_{g}",
    )

    venue_id      = None
    resolved_name = ""

    if platform == "resy":
        st.markdown(
            '<p style="color:#1a3458;font-size:0.76rem;margin:0.15rem 0 0.45rem;">'
            'Paste the Resy URL from your browser for the restaurant you want to monitor.</p>',
            unsafe_allow_html=True,
        )
        resy_url = st.text_input(
            "Resy URL",
            placeholder="https://resy.com/cities/new-york-ny/venues/lilia",
            key=f"f_resy_url_{g}",
        )
        if resy_url and "/venues/" in resy_url:
            with st.spinner("Looking up venue…"):
                info = lookup_resy_venue(resy_url)
            if info:
                venue_id      = info["venue_id"]
                resolved_name = info["name"]
                meta = " · ".join(filter(None, [info.get("neighborhood", ""), info.get("cuisine", "")]))
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#070d20,#060e1c);'
                    f'border:1px solid #0f2040;border-radius:10px;'
                    f'padding:0.7rem 1rem;margin:0.3rem 0 0.6rem;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="color:#c8d8f0;font-weight:600;font-size:0.92rem;">{info["name"]}</span>'
                    f'<span style="background:#1d4ed81a;color:#60a5fa;padding:2px 10px;'
                    f'border-radius:999px;font-size:0.7rem;font-weight:700;">'
                    f'ID&nbsp;{venue_id}</span>'
                    f'</div>'
                    f'<span style="color:#1a3458;font-size:0.74rem;">{meta}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning("Couldn't resolve that URL — check it's a valid Resy restaurant page.")
    else:
        st.markdown(
            '<p style="color:#1a3458;font-size:0.76rem;margin:0.15rem 0 0.45rem;">'
            'Go to <a href="https://www.opentable.com" target="_blank" '
            'style="color:#38bdf8;text-decoration:none;">opentable.com</a>, open the restaurant '
            'page, and copy the <code style="color:#38bdf8;background:#060e1c;'
            'padding:1px 5px;border-radius:4px;">rid=XXXXX</code> from the URL.</p>',
            unsafe_allow_html=True,
        )
        resolved_name = st.text_input(
            "Restaurant Name",
            placeholder="e.g. Carbone",
            key=f"f_ot_name_{g}",
        )
        venue_id = st.number_input(
            "OpenTable rid",
            min_value=1,
            value=1,
            step=1,
            key=f"f_ot_id_{g}",
        )

    st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
    _h("Reservation Details")

    res_date = st.date_input(
        "Date",
        value=date.today() + timedelta(days=1),
        key=f"f_date_{g}",
    )
    tc1, tc2 = st.columns(2)
    with tc1:
        earliest = st.text_input("Earliest Time", value="18:00", key=f"f_earliest_{g}")
    with tc2:
        latest = st.text_input("Latest Time", value="22:00", key=f"f_latest_{g}")
    party = st.number_input(
        "Party Size",
        min_value=1,
        max_value=20,
        value=2,
        key=f"f_party_{g}",
    )

    # ── Pending list ──────────────────────────────────────────────────────────
    pending = st.session_state.pending
    if pending:
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        _h(f"Queued  ({len(pending)})")
        for r in list(pending):
            color = "#3b82f6" if r["platform"] == "resy" else "#22d3ee"
            ci, cb = st.columns([10, 1])
            with ci:
                st.markdown(
                    f'<div style="padding:0.4rem 0;border-bottom:1px solid #090f1e;">'
                    f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:2px;">'
                    f'<span style="color:#c8d8f0;font-weight:600;font-size:0.86rem;">{r["name"]}</span>'
                    f'{_badge(r["platform"], color)}'
                    f'</div>'
                    f'<span style="color:#162040;font-size:0.73rem;">'
                    f'{r["date"]} · {r["earliest"]}–{r["latest"]} · party&nbsp;{r["party_size"]}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
            with cb:
                if st.button("✕", key=f"rm_{r['id']}"):
                    st.session_state.pending = [x for x in pending if x["id"] != r["id"]]
                    st.rerun()

    st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)

    # ── "Add Another" button ──────────────────────────────────────────────────
    def _build_entry():
        return {
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

    def _validate():
        if platform == "resy" and not venue_id:
            st.error("Paste a valid Resy URL so the venue can be identified.")
            return False
        if platform == "opentable" and not resolved_name.strip():
            st.error("Enter the restaurant name.")
            return False
        if earliest >= latest:
            st.error("Earliest must be before latest time.")
            return False
        return True

    if st.button("＋  Add Another Restaurant", key="btn_add_another", use_container_width=True):
        if _validate():
            st.session_state.pending.append(_build_entry())
            st.session_state.next_id  += 1
            st.session_state.form_gen += 1   # reset form
            st.rerun()

    # ── Settings + Start ─────────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    _h("Settings")

    phone = st.text_input(
        "Phone Number (10 digits, T-Mobile SMS gateway)",
        placeholder="2125551234",
        max_chars=10,
        key="s_phone",
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        freq = st.number_input(
            "Check Every (minutes)",
            min_value=1, max_value=120, value=5,
            key="s_freq",
        )
    with sc2:
        stop_date = st.date_input(
            "Auto-stop After",
            value=date.today() + timedelta(days=7),
            key="s_stop",
        )

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    if not active:
        # Green gradient Start button via JS injection
        _components.html("""<script>
            (function paint() {
                const btns = window.parent.document.querySelectorAll(
                    '[data-testid="baseButton-primary"]');
                let found = false;
                btns.forEach(b => {
                    if (b.innerText.includes('Start Monitoring')) {
                        b.style.setProperty('background',
                            'linear-gradient(135deg,#15803d,#0d6e56)', 'important');
                        b.style.setProperty('box-shadow',
                            '0 2px 18px rgba(21,128,61,0.4)', 'important');
                        found = true;
                    }
                });
                if (!found) setTimeout(paint, 80);
            })();
        </script>""", height=0)

        if st.button("▶  Start Monitoring", key="btn_start", type="primary", use_container_width=True):
            phone_val = (phone or "").strip()
            # Auto-include the current form if it's filled out and not already queued
            all_restaurants = list(st.session_state.pending)
            form_filled = (platform == "resy" and venue_id) or (platform == "opentable" and resolved_name.strip())
            if form_filled and _validate():
                all_restaurants.append(_build_entry())
                st.session_state.next_id += 1

            if not all_restaurants:
                st.error("Add at least one restaurant first.")
            elif len(phone_val) != 10 or not phone_val.isdigit():
                st.error("Enter a valid 10-digit phone number.")
            elif not GMAIL_FROM or not GMAIL_PASSWORD:
                st.error("Gmail credentials not configured (config.py).")
            else:
                _start(all_restaurants, int(freq) * 60, stop_date, f"{phone_val}@tmomail.net")
                st.session_state.pending  = []
                st.session_state.form_gen += 1
                st.rerun()
    else:
        if st.button("⏹  Stop Monitoring", key="btn_stop", type="primary", use_container_width=True):
            _stop_all()
            st.rerun()

        # Add-more shortcut while monitoring is active
        if st.button("＋  Add to Active Monitor", key="btn_add_live", use_container_width=True):
            form_filled = (platform == "resy" and venue_id) or (platform == "opentable" and resolved_name.strip())
            if form_filled and _validate():
                entry = _build_entry()
                with _lock:
                    _ms["restaurants"].append(entry)
                _log("INFO", f"[{entry['id']}] {entry['name']} added to active watch list.")
                st.session_state.next_id  += 1
                st.session_state.form_gen += 1
                st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    render_header()
    render_active_status()
    render_form()
    render_log()


main()
