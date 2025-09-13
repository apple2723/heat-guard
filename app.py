
# HeatGuard — Python-only (Streamlit)
#
# Run:
#   pip install -r requirements.txt
#   streamlit run app.py
#
# Uses an OpenWeather API key from: https://home.openweathermap.org/api_keys
# 

from dotenv import load_dotenv
load_dotenv()  # <- loads your .env file first

import os
import math
import time
import requests
import datetime as dt
import streamlit as st

# ----------------------
# Config & Utilities
# ----------------------
st.set_page_config(page_title="HeatGuard", page_icon="🌡️", layout="centered")

def get_api_key():
    # Prefer env var; allow sidebar override
    env = os.environ.get("OPENWEATHER_KEY", "").strip()
    ui = st.session_state.get("OPENWEATHER_KEY_UI", "").strip()
    return ui or env

def f_to_c(f):
    return (f - 32.0) * 5.0/9.0

def c_to_f(c):
    return c * 9.0/5.0 + 32.0

# Rothfusz regression (NOAA) for Heat Index (Fahrenheit)
def heat_index_f(T_f, RH):
    c1 = -42.379
    c2 = 2.04901523
    c3 = 10.14333127
    c4 = -0.22475541
    c5 = -0.00683783
    c6 = -0.05481717
    c7 = 0.00122874
    c8 = 0.00085282
    c9 = -0.00000199
    HI = (c1 + c2*T_f + c3*RH + c4*T_f*RH + c5*(T_f**2) + c6*(RH**2)
          + c7*(T_f**2)*RH + c8*T_f*(RH**2) + c9*(T_f**2)*(RH**2))
    # Adjustments
    if RH < 13 and 80 <= T_f <= 112:
        adj = ((13 - RH)/4) * math.sqrt((17 - abs(T_f - 95))/17)
        HI -= adj
    elif RH > 85 and 80 <= T_f <= 87:
        adj = ((RH - 85)/10) * ((87 - T_f)/5)
        HI += adj
    return HI

def risk_from_hi(hi_f):
    if hi_f >= 125: return "Extreme", "🔴"
    if hi_f >= 104: return "High", "🟠"
    if hi_f >=  90: return "Moderate", "🟡"
    return "Low", "🟢"

def fmt_hour(ts, tz_offset_seconds=0):
    # ts is unix UTC
    local = dt.datetime.utcfromtimestamp(ts + tz_offset_seconds)
    return local.strftime("%-I%p")

def fmt_range(start_ts, end_ts, tz_offset_seconds=0):
    a = dt.datetime.utcfromtimestamp(start_ts + tz_offset_seconds)
    b = dt.datetime.utcfromtimestamp(end_ts + tz_offset_seconds)
    if a == b: return a.strftime("%-I%p")
    return f"{a.strftime('%-I%p')}–{b.strftime('%-I%p')}"

# Role rules (base)
ROLE_RULES = {
    "Student athlete (13–18)": dict(work=45, rest=15, ml_per_20=250, note="Light-colored gear; buddy checks."),
    "Construction":            dict(work=40, rest=20, ml_per_20=300, note="Use shade canopies; rotate tasks."),
    "Delivery / courier":      dict(work=50, rest=10, ml_per_20=250, note="Cold packs in bag; short stops in shade."),
    "Elderly outdoors":        dict(work=30, rest=30, ml_per_20=200, note="Frequent sips; caregiver check."),
}

def adjust_rules_for_risk(role, peak_risk):
    base = ROLE_RULES[role].copy()
    work, rest = base["work"], base["rest"]
    if peak_risk == "High":
        work = max(20, work - 10)
        rest = rest + 10
    elif peak_risk == "Extreme":
        work = max(15, work - 15)
        rest = rest + 15
    base["work"], base["rest"] = work, rest
    return base

def hydration_schedule(total_minutes, ml_per_20):
    # Return a list of (minute, amount_ml)
    schedule = []
    t = 20
    while t <= total_minutes:
        schedule.append((t, ml_per_20))
        t += 20
    return schedule

# ----------------------
# Sidebar Controls
# ----------------------
st.sidebar.title("HeatGuard Settings")
st.sidebar.write("Provide a location and API key to generate your plan.")

roles = list(ROLE_RULES.keys())
role = st.sidebar.selectbox("Role", roles, index=0)

duration = st.sidebar.slider("Session duration (minutes)", 30, 240, 90, 10)

units = st.sidebar.radio("Units", ["Fahrenheit (°F)", "Celsius (°C)"], index=0)

api_key_ui = st.sidebar.text_input("OpenWeather API Key (optional, else use env)",
                                   type="password",
                                   value=st.session_state.get("OPENWEATHER_KEY_UI", ""))
st.session_state["OPENWEATHER_KEY_UI"] = api_key_ui

st.sidebar.write("---")
st.sidebar.caption("Location options: (A) use coordinates, or (B) geocode a city name.")

lat = st.sidebar.text_input("Latitude", "")
lon = st.sidebar.text_input("Longitude", "")
city = st.sidebar.text_input("Or city name (e.g., 'Phoenix,US' or 'Delhi,IN')", "")

# ----------------------
# Main UI
# ----------------------
st.title("🌡️ HeatGuard — Heat Risk Coach")

st.markdown(
"""Turn weather into action. Get a **heat risk score**, **safe outdoor windows**, and a **hydration + break plan** tailored to your activity.
"""
)

api_key = get_api_key()
if not api_key:
    st.warning("Add your OpenWeather API key in the sidebar (or set env var OPENWEATHER_KEY).")

# Location resolution
resolved = None
tz_offset = 0

colA, colB = st.columns(2)
with colA:
    go = st.button("Build my plan", type="primary")
with colB:
    demo = st.button("Try a demo location (Phoenix, AZ)")

if demo and not go:
    lat, lon = "33.45", "-112.07"  # Phoenix
    city = ""

if go or demo:
    try:
        if (lat and lon):
            lat_f = float(lat); lon_f = float(lon)
            resolved = dict(lat=lat_f, lon=lon_f, label=f"{lat_f:.2f},{lon_f:.2f}")
        elif city:
            # Geocoding via OpenWeather Direct Geocoding API
            url = f"https://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={api_key}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            arr = r.json()
            if not arr:
                st.error("City not found. Try adding country code, e.g., 'Delhi,IN'.")
            else:
                resolved = dict(lat=arr[0]["lat"], lon=arr[0]["lon"],
                                label=f"{arr[0].get('name','?')}, {arr[0].get('country','?')}")
        else:
            st.error("Provide either coordinates or a city name.")
    except Exception as e:
        st.error(f"Location error: {e}")

# Fetch forecast & analyze
if resolved and api_key:
    try:
        # Use One Call API (2.5). Units: imperial -> Fahrenheit from API.
        url = f"https://api.openweathermap.org/data/2.5/onecall?lat={resolved['lat']}&lon={resolved['lon']}&units=imperial&exclude=minutely,daily,alerts&appid={api_key}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        tz_offset = data.get("timezone_offset", 0)

        hourly = data.get("hourly", [])[:24]  # next 24 hours
        if not hourly:
            st.error("No hourly forecast returned.")
        else:
            # Compute HI & risk
            rows = []
            for h in hourly:
                T_f = h.get("temp")            # already in F (imperial)
                RH  = h.get("humidity", 0)     # in %
                UVI = h.get("uvi", 0.0) or 0.0
                HI  = heat_index_f(T_f, RH)
                # Optional "UV bump" of +3°F for UVI >= 8
                if UVI >= 8:
                    HI += 3.0
                risk, emoji = risk_from_hi(HI)
                rows.append({
                    "ts": h["dt"],
                    "temp_f": T_f,
                    "rh": RH,
                    "uvi": UVI,
                    "hi_f": HI,
                    "risk": risk,
                    "emoji": emoji,
                    "hour": fmt_hour(h["dt"], tz_offset),
                })

            # Peak risk
            peak = max(rows, key=lambda r: r["hi_f"])
            peak_risk = peak["risk"]
            peak_hi   = round(peak["hi_f"])

            # Safe windows: contiguous Low/Moderate
            good_idxs = [i for i,rw in enumerate(rows) if rw["risk"] in ("Low","Moderate")]
            windows = []
            i = 0
            while i < len(good_idxs):
                start_i = good_idxs[i]
                end_i = start_i
                while i+1 < len(good_idxs) and good_idxs[i+1] == end_i + 1:
                    i += 1
                    end_i = good_idxs[i]
                windows.append((rows[start_i]["ts"], rows[end_i]["ts"]))
                i += 1

            # Render
            st.success(f"Location: **{resolved['label']}**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Peak Heat Index (next 24h)", f"{peak_hi} °F", help="Approximate apparent temperature due to heat + humidity.")
                st.write(f"**Peak risk:** {peak_risk} {dict(Low='🟢',Moderate='🟡',High='🟠',Extreme='🔴')[peak_risk]}")
            with col2:
                if windows:
                    chips = ", ".join([fmt_range(a,b, tz_offset) for a,b in windows])
                    st.metric("Safer Outdoor Windows", chips)
                else:
                    st.metric("Safer Outdoor Windows", "None — keep sessions short & shaded")

            # Table preview
            import pandas as pd
            df = pd.DataFrame([{
                "Hour": r["hour"],
                "Temp (°F)": round(r["temp_f"]),
                "RH (%)": r["rh"],
                "UVI": r["uvi"],
                "Heat Index (°F)": round(r["hi_f"]),
                "Risk": f"{r['emoji']} {r['risk']}",
            } for r in rows])
            st.dataframe(df, use_container_width=True)

            # Guidance
            rules = adjust_rules_for_risk(role, peak_risk)
            st.subheader("Personalized Guidance")
            st.markdown(f"""
- **Role:** {role}  
- **Work/Rest Cycle:** **{rules['work']} min work** / **{rules['rest']} min shade**  
- **Hydration:** **{rules['ml_per_20']} ml every 20 min**  
- **Note:** {rules['note']}
""")

            # Hydration plan timeline
            sched = hydration_schedule(duration, rules["ml_per_20"])
            if sched:
                st.markdown("**Hydration Reminders** (relative to session start):")
                st.write(", ".join([f"{m} min" for m,_ in sched]))
            else:
                st.write("Session shorter than 20 minutes — still bring water.")

            # Printable daily bulletin
            st.subheader("Printable Daily Bulletin")
            safe_text = ", ".join([fmt_range(a,b, tz_offset) for a,b in windows]) if windows else "None"
            bulletin = f"""HEATGUARD DAILY BULLETIN
Location: {resolved['label']}
Peak Heat Index: {peak_hi} °F
Peak Risk: {peak_risk}
Safer Outdoor Windows: {safe_text}

Role: {role}
Work/Rest: {rules['work']} / {rules['rest']} (min)
Hydration: {rules['ml_per_20']} ml every 20 min
Note: {rules['note']}

Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
            st.download_button("Download bulletin (.txt)", bulletin, file_name="heatguard_bulletin.txt")

            # Simple reminder ticker (visual only)
            st.subheader("Session Reminder (visual aid)")
            if "timer_start" not in st.session_state:
                if st.button("Start Session Timer"):
                    st.session_state["timer_start"] = time.time()
                    st.rerun()
            else:
                elapsed = int(time.time() - st.session_state["timer_start"])
                st.write(f"Elapsed: **{elapsed//60}m {elapsed%60}s**")
                # Show next hydration mark
                next_marks = [m for m,_ in sched if m*60 > elapsed]
                nxt = next_marks[0] if next_marks else None
                if nxt:
                    st.info(f"Next hydration reminder at **{nxt} min**.")
                else:
                    st.success("Hydration schedule complete for this session.")
                if st.button("Reset Timer"):
                    del st.session_state["timer_start"]
                    st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

st.caption("Tip: this Python app uses Streamlit + OpenWeather")
