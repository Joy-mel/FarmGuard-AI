"""
FarmGuard AI - Live Dashboard (Streamlit)
============================================
A live monitoring dashboard for farmers and agricultural managers.
Talks to the FastAPI backend (api/main.py) over HTTP - it never imports
the model code directly, so this dashboard can be deployed completely
separately from the API (e.g. Streamlit Community Cloud + Cloud Run).

Configure the backend location with an environment variable so this works
both locally and once deployed:
    export FARMGUARD_API_URL="https://your-api.example.com"
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501

Run locally against a local API:
    streamlit run app.py
"""

import os
from datetime import datetime

import requests
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

API_URL = os.environ.get("FARMGUARD_API_URL", "http://localhost:8000").rstrip("/")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

st.set_page_config(
    page_title="FarmGuard AI",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Dark green agricultural theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #0f1f13; color: #e8f0e9; }
    section[data-testid="stSidebar"] { background-color: #142a19; }
    h1, h2, h3 { color: #7bc47f !important; }
    div[data-testid="stMetric"] {
        background-color: #1a3320; border: 1px solid #2d5233;
        border-radius: 10px; padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] { color: #a8c9ac !important; }
    div[data-testid="stMetricValue"] { color: #ffffff !important; }
    .stButton>button {
        background-color: #2e7d32; color: white; border: none;
        border-radius: 8px; font-weight: 600; padding: 10px 20px;
    }
    .stButton>button:hover { background-color: #3e9142; }
    .banner-fallback {
        background: linear-gradient(135deg, #1a3320, #2e7d32);
        border-radius: 12px; padding: 40px; text-align: center;
        font-size: 40px;
    }
    .risk-badge {
        display: inline-block; padding: 6px 14px; border-radius: 20px;
        font-weight: 700; font-size: 14px;
    }
    .risk-drought { background: #7a2e22; color: #ffb4a3; }
    .risk-flood { background: #1f4e79; color: #a3d1ff; }
    .risk-heat_stress { background: #7a5c1f; color: #ffdf9e; }
    .risk-normal { background: #1e5c28; color: #a3ffb0; }
</style>
""", unsafe_allow_html=True)


def safe_image(col, path, fallback_emoji="🌾", caption=None):
    """Show a local image if it exists; otherwise render a graceful
    placeholder instead of crashing the whole dashboard."""
    if path and os.path.exists(path):
        col.image(path, use_container_width=True, caption=caption)
    else:
        col.markdown(f'<div class="banner-fallback">{fallback_emoji}</div>', unsafe_allow_html=True)
        if caption:
            col.caption(caption)


@st.cache_data(ttl=300)
def fetch_counties():
    try:
        r = requests.get(f"{API_URL}/api/counties", timeout=10)
        r.raise_for_status()
        return sorted([c["name"] for c in r.json()["counties"]])
    except Exception:
        return ["nairobi", "kisumu", "mombasa", "eldoret", "nakuru", "machakos"]  # offline fallback


@st.cache_data(ttl=120)
def fetch_prediction(location, crop, overrides=None):
    payload = {"location": location, "crop": crop, **(overrides or {})}
    r = requests.post(f"{API_URL}/predict", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_prediction_uncached(location, crop, overrides=None):
    """Used by the simulator form - always hits the API fresh since the
    whole point is testing different manual inputs, not reusing a cached
    result from a previous slider position."""
    payload = {"location": location, "crop": crop, **(overrides or {})}
    r = requests.post(f"{API_URL}/predict", json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_history(location):
    try:
        r = requests.get(f"{API_URL}/api/history", params={"location": location}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Header banner
# ---------------------------------------------------------------------------
banner_col, title_col = st.columns([1, 2])
safe_image(banner_col, os.path.join(ASSETS_DIR, "banner.png"), fallback_emoji="🌾", caption=None)
with title_col:
    st.title("FarmGuard AI")
    st.markdown("**Live climate risk & market price monitoring for Kenyan farmers**")
    st.caption(f" {datetime.now().strftime('%A, %d %B %Y')}")

st.divider()

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("Select farm")
counties = fetch_counties()
default_idx = counties.index("nairobi") if "nairobi" in counties else 0
location = st.sidebar.selectbox("County", counties, index=default_idx)
crop = st.sidebar.selectbox("Crop", ["maize", "beans"])
st.sidebar.divider()
logo_col = st.sidebar
safe_image(logo_col, os.path.join(ASSETS_DIR, "logo.png"), fallback_emoji="🌱", caption="FarmGuard AI")

# ---------------------------------------------------------------------------
# Live metric cards
# ---------------------------------------------------------------------------
try:
    live = fetch_prediction(location, crop)
    api_reachable = True
except Exception as e:
    api_reachable = False
    live = None
    st.error(f"Couldn't reach the FarmGuard API at {API_URL}. Is it running? ({e})")

if live:
    risk = live["climate_risk"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Soil Moisture", f"{live['soil_moisture_pct']}%")
    m2.metric("NDVI (Vegetation)", f"{live['ndvi']}", live["vegetation_health"])
    m3.metric(f"{crop.title()} Price", f"KES {live['current_price_kes_per_kg']}/kg",
              f"{live['price_change_pct']:+.1f}% forecast")
    with m4:
        st.markdown(f"**AI Risk Alert**")
        st.markdown(f'<span class="risk-badge risk-{risk}">{risk.upper().replace("_", " ")}</span>',
                    unsafe_allow_html=True)
        st.caption(f"Model accuracy: {live['risk_model_accuracy_pct']}%")

    st.divider()

    rec_col, soil_col = st.columns([2, 1])
    with rec_col:
        st.subheader("Recommendations")
        for rec in live["recommendations"]:
            st.markdown(f"- {rec}")
    with soil_col:
        st.subheader("Soil Profile")
        st.write(f"**Type:** {live['soil_type']}")
        st.caption("Zone-level approximation - see ARCHITECTURE.md for real soil API options.")

    st.divider()

    # -----------------------------------------------------------------
    # Historical trend chart (Plotly)
    # -----------------------------------------------------------------
    st.subheader("14-Day Trend")
    hist = fetch_history(location)

    if hist:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["days"], y=hist["soil_moisture"], name="Soil Moisture (%)",
                                  line=dict(color="#7bc47f", width=3)))
        fig.add_trace(go.Scatter(x=hist["days"], y=hist["temp_mean"], name="Temp (°C)",
                                  line=dict(color="#ffb703", width=3, dash="dot"), yaxis="y2"))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#0f1f13", plot_bgcolor="#0f1f13",
            xaxis=dict(title="Date"),
            yaxis=dict(title="Soil Moisture (%)", side="left"),
            yaxis2=dict(title="Temperature (°C)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.15),
            margin=dict(l=10, r=10, t=30, b=10), height=380,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Trend data unavailable - couldn't reach /api/history.")

st.divider()

# ---------------------------------------------------------------------------
# Prediction Simulator
# ---------------------------------------------------------------------------
st.subheader("Prediction Simulator")
st.caption("Manually enter sensor readings to see what FarmGuard AI would predict for that exact input.")

with st.form("simulator"):
    c1, c2, c3 = st.columns(3)
    sim_temp = c1.slider("Temperature (°C)", -5.0, 50.0, 27.0)
    sim_rain = c1.slider("Rainfall (mm/day)", 0.0, 100.0, 5.0)
    sim_moisture = c2.slider("Soil Moisture (%)", 0.0, 100.0, 35.0)
    sim_humidity = c2.slider("Humidity (%)", 0.0, 100.0, 60.0)
    sim_et = c3.slider("Evapotranspiration (mm/day)", 0.0, 15.0, 4.5)
    submitted = st.form_submit_button("Run FarmGuard AI Prediction")

if submitted:
    try:
        overrides = {
            "temperature_c": sim_temp, "rainfall_mm": sim_rain,
            "soil_moisture_pct": sim_moisture, "humidity_pct": sim_humidity,
            "evapotranspiration_mm": sim_et,
        }
        result = fetch_prediction_uncached(location, crop, overrides)
        risk = result["climate_risk"]
        st.markdown(f'<span class="risk-badge risk-{risk}">{risk.upper().replace("_", " ")}</span>',
                    unsafe_allow_html=True)
        st.write(f"**{crop.title()} price forecast:** KES {result['forecast_price_kes_per_kg']}/kg "
                 f"({result['price_change_pct']:+.1f}% from current KES {result['current_price_kes_per_kg']}/kg)")
        st.markdown("**Recommendations:**")
        for rec in result["recommendations"]:
            st.markdown(f"- {rec}")
    except Exception as e:
        st.error(f"Simulation failed: {e}")

st.divider()
st.caption(
    "FarmGuard AI covers all 47 Kenyan counties. Weather and market-price data "
    "are illustrative in this demo - see ARCHITECTURE.md for swapping in live feeds."
)
