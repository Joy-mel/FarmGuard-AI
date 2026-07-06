"""
FarmGuard AI - Core Prediction Pipeline
=========================================
Covers all 47 Kenyan counties (see kenya_counties.py). Trains once per
county, persists to disk (joblib), and serves predictions instantly from
the saved bundle - no retraining on every request.
"""

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import joblib

from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

from kenya_counties import KENYA_COUNTIES, get_zone_soil, get_coords

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Backward/forward-compatible alias: {name: (lat, lon)} for all 47 counties
DEFAULT_LOCATIONS = {name: (lat, lon) for name, (lat, lon, zone) in KENYA_COUNTIES.items()}


# ---------------------------------------------------------------------------
# 1. DATA FETCHING
# ---------------------------------------------------------------------------

def fetch_weather_data(lat=-1.2921, lon=36.8219, days=365):
    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=days)
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "daily": [
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum", "rain_sum", "windspeed_10m_max",
            "et0_fao_evapotranspiration", "soil_moisture_0_to_7cm",
        ],
        "timezone": "Africa/Nairobi",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame({
            "date": pd.to_datetime(data["daily"]["time"]),
            "temp_max": data["daily"]["temperature_2m_max"],
            "temp_min": data["daily"]["temperature_2m_min"],
            "temp_mean": data["daily"]["temperature_2m_mean"],
            "rainfall": data["daily"]["precipitation_sum"],
            "windspeed": data["daily"]["windspeed_10m_max"],
            "evapotranspiration": data["daily"]["et0_fao_evapotranspiration"],
            "soil_moisture": data["daily"]["soil_moisture_0_to_7cm"],
        }).fillna(0)
        df["humidity_estimate"] = (100 - df["evapotranspiration"] * 10).clip(30, 95)
        return df
    except Exception:
        return _synthetic_weather(days, lat)


def _synthetic_weather(days, lat=-1.2921):
    """Fallback used when Open-Meteo is unreachable. Rough latitude-aware
    seasonality so arid-north counties don't get the same rainfall profile
    as the lake basin."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    doy = np.array([d.timetuple().tm_yday for d in dates])
    aridity = max(0.3, 1 - abs(lat) / 5)  # rough: further from equator band -> drier baseline in this toy model
    rainfall = np.maximum(0, 3 * aridity + 10 * aridity * np.sin(2 * np.pi * doy / 365) + np.random.normal(0, 5, days))
    temp_mean = 24 + 6 * np.sin(2 * np.pi * (doy - 80) / 365) + np.random.normal(0, 2, days)
    return pd.DataFrame({
        "date": dates, "temp_mean": temp_mean, "temp_max": temp_mean + 5,
        "temp_min": temp_mean - 5, "rainfall": rainfall,
        "soil_moisture": np.clip(np.random.uniform(15, 80, days) * aridity + 10, 5, 90),
        "humidity_estimate": np.random.uniform(40, 85, days),
        "evapotranspiration": np.random.uniform(2, 7, days),
        "windspeed": np.random.uniform(5, 20, days),
    })


def fetch_ndvi(lat=-1.2921, lon=36.8219):
    dates = pd.date_range(end=datetime.now(), periods=52, freq="W")
    doy = np.array([d.timetuple().tm_yday for d in dates])
    ndvi = np.clip(0.5 + 0.2 * np.sin(2 * np.pi * doy / 365) + np.random.normal(0, 0.05, len(dates)), 0.15, 0.85)
    df = pd.DataFrame({"date": dates, "ndvi": ndvi})
    conditions = [df["ndvi"] < 0.3, (df["ndvi"] >= 0.3) & (df["ndvi"] < 0.5),
                  (df["ndvi"] >= 0.5) & (df["ndvi"] < 0.7), df["ndvi"] >= 0.7]
    df["vegetation_health"] = np.select(conditions, ["Poor", "Moderate", "Good", "Excellent"], default="Unknown")
    return df


def get_soil_info(lat=-1.2921, lon=36.8219, location_name="nairobi"):
    """See kenya_counties.py docstring for the honesty note on this being
    zone-level approximation, not surveyed per-county data."""
    return get_zone_soil(location_name)


# ---------------------------------------------------------------------------
# 2. LABELS + MODEL TRAINING
# ---------------------------------------------------------------------------

def label_climate_risk(df):
    risks, alerts = [], []
    for _, row in df.iterrows():
        if row["rainfall"] < 2 and row["soil_moisture"] < 30:
            risks.append("drought")
            alerts.append(f"DROUGHT ALERT: soil moisture {row['soil_moisture']:.1f}%")
        elif row["rainfall"] > 40:
            risks.append("flood")
            alerts.append(f"FLOOD RISK: {row['rainfall']:.1f}mm rainfall")
        elif row["temp_max"] > 30:
            risks.append("heat_stress")
            alerts.append(f"HEAT STRESS: {row['temp_max']:.1f}°C")
        else:
            risks.append("normal")
            alerts.append(None)
    df["risk"] = risks
    df["alert"] = alerts
    return df


def train_risk_model(df):
    features = ["temp_mean", "rainfall", "soil_moisture", "humidity_estimate", "evapotranspiration"]
    X, y = df[features], df["risk"]
    if y.nunique() < 2:
        # degenerate case (e.g. one class only) - still fit, just skip stratify
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    model = GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, max_depth=5, random_state=42)
    model.fit(X_train, y_train)
    acc = accuracy_score(y_test, model.predict(X_test))
    return model, acc, features


def create_market_data(weather_df):
    df = weather_df.copy()
    base_maize, base_beans = 50, 90
    season = 5 * np.sin(2 * np.pi * df["date"].dt.dayofyear / 365)
    rainfall_factor = -0.3 * (df["rainfall"] - df["rainfall"].mean()) / (df["rainfall"].std() or 1)
    temp_factor = 0.5 * (df["temp_mean"] - df["temp_mean"].mean())
    df["maize_price"] = np.maximum(30, base_maize + rainfall_factor + season + np.random.normal(0, 3, len(df)))
    df["beans_price"] = np.maximum(60, base_beans + temp_factor + season + np.random.normal(0, 4, len(df)))
    demand_season = 15 * np.sin(2 * np.pi * (df["date"].dt.dayofyear - 60) / 365)
    df["demand_index"] = np.clip(60 + demand_season + np.random.normal(0, 8, len(df)), 20, 100)
    return df


def train_price_model(df, crop):
    price_col = f"{crop}_price"
    d = df.copy()
    d["price_lag1"] = d[price_col].shift(1)
    d["price_lag7"] = d[price_col].shift(7)
    d["price_ma7"] = d[price_col].rolling(7).mean()
    d["rainfall_ma7"] = d["rainfall"].rolling(7).mean()
    d["temp_ma7"] = d["temp_mean"].rolling(7).mean()
    d["demand_lag1"] = d["demand_index"].shift(1)
    d["day_of_year"] = d["date"].dt.dayofyear
    d["month"] = d["date"].dt.month
    d = d.dropna()

    features = ["price_lag1", "price_lag7", "price_ma7", "rainfall_ma7",
                "temp_ma7", "demand_lag1", "day_of_year", "month"]
    X, y = d[features], d[price_col]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestRegressor(n_estimators=150, max_depth=10, min_samples_split=5, random_state=42)
    model.fit(X_train, y_train)
    mae = mean_absolute_error(y_test, model.predict(X_test))
    return model, mae, features, d


# ---------------------------------------------------------------------------
# 3. RECOMMENDATION ENGINE
# ---------------------------------------------------------------------------

def generate_recommendations(climate_risk, price_forecast, current_price, soil_moisture, crop="maize"):
    lines = []
    if climate_risk == "drought":
        lines += ["DROUGHT ALERT - act now",
                  f"Soil moisture {soil_moisture:.1f}% - conserve water",
                  "Consider drought-resistant seed varieties",
                  "Check irrigation and storage tanks"]
    elif climate_risk == "flood":
        lines += ["FLOOD RISK - prepare drainage",
                  "Clear field drainage channels",
                  "Delay planting if ground is waterlogged"]
    elif climate_risk == "heat_stress":
        lines += ["HEAT STRESS WARNING",
                  "Increase watering frequency",
                  "Watch for pests, which thrive in heat",
                  "Apply mulch to retain soil moisture"]
    else:
        lines += ["NORMAL CONDITIONS - good for planting/field work",
                  f"Soil moisture adequate ({soil_moisture:.1f}%)"]

    change = ((price_forecast - current_price) / current_price) * 100
    if change > 5:
        lines += [f"{crop.upper()} price rising (+{change:.1f}% forecast)",
                  f"Now: KES {current_price:.2f}/kg -> Forecast: KES {price_forecast:.2f}/kg",
                  "Consider holding stock 2-4 weeks if storage allows"]
    elif change < -5:
        lines += [f"{crop.upper()} price falling ({change:.1f}% forecast)",
                  f"Now: KES {current_price:.2f}/kg -> Forecast: KES {price_forecast:.2f}/kg",
                  "Consider selling soon before prices drop further"]
    else:
        lines += [f"{crop.upper()} price stable ({change:+.1f}% forecast)",
                  "Normal selling conditions"]
    return lines


# ---------------------------------------------------------------------------
# 4. TRAIN + PERSIST
# ---------------------------------------------------------------------------

def build_and_save_models(lat=-1.2921, lon=36.8219, location_name="nairobi"):
    weather_df = fetch_weather_data(lat, lon)
    weather_df = label_climate_risk(weather_df)
    risk_model, risk_acc, risk_features = train_risk_model(weather_df)

    market_df = create_market_data(weather_df)
    maize_model, maize_mae, maize_features, _ = train_price_model(market_df, "maize")
    beans_model, beans_mae, beans_features, _ = train_price_model(market_df, "beans")

    ndvi_df = fetch_ndvi(lat, lon)
    soil_info = get_soil_info(lat, lon, location_name)

    bundle = {
        "risk_model": risk_model, "risk_features": risk_features, "risk_acc": risk_acc,
        "maize_model": maize_model, "maize_features": maize_features, "maize_mae": maize_mae,
        "beans_model": beans_model, "beans_features": beans_features, "beans_mae": beans_mae,
        "soil_info": soil_info,
        "latest_weather": weather_df.tail(14).to_dict(orient="records"),
        "latest_market": market_df.tail(14).to_dict(orient="records"),
        "latest_ndvi": ndvi_df.tail(4).to_dict(orient="records"),
        "trained_at": datetime.now().isoformat(),
        "location": {"name": location_name, "lat": lat, "lon": lon},
    }
    path = os.path.join(MODEL_DIR, f"{location_name}.joblib")
    joblib.dump(bundle, path)
    return path, bundle


def load_bundle(location_name="nairobi"):
    path = os.path.join(MODEL_DIR, f"{location_name}.joblib")
    if not os.path.exists(path):
        lat, lon = get_coords(location_name)
        _, bundle = build_and_save_models(lat, lon, location_name)
        return bundle
    return joblib.load(path)


def predict_for_farmer(location_name="nairobi", crop="maize", sensor_overrides=None):
    """Single entry point used by the API, WhatsApp bot, and dashboard."""
    sensor_overrides = sensor_overrides or {}
    used_override = bool(sensor_overrides)

    bundle = load_bundle(location_name)
    latest_weather = pd.DataFrame(bundle["latest_weather"]).iloc[-1].copy()
    latest_market = pd.DataFrame(bundle["latest_market"]).iloc[-1]
    ndvi_latest = pd.DataFrame(bundle["latest_ndvi"]).iloc[-1]

    field_map = {
        "temperature_c": "temp_mean",
        "rainfall_mm": "rainfall",
        "soil_moisture_pct": "soil_moisture",
        "humidity_pct": "humidity_estimate",
        "evapotranspiration_mm": "evapotranspiration",
    }
    for api_field, internal_field in field_map.items():
        if sensor_overrides.get(api_field) is not None:
            latest_weather[internal_field] = sensor_overrides[api_field]

    risk_features = bundle["risk_features"]
    X_risk = pd.DataFrame([latest_weather[risk_features].to_dict()])
    predicted_risk = bundle["risk_model"].predict(X_risk)[0]

    crop = crop.lower()
    model_key = "maize_model" if crop == "maize" else "beans_model"
    features = bundle["maize_features"] if crop == "maize" else bundle["beans_features"]
    price_col = "maize_price" if crop == "maize" else "beans_price"

    market_hist = pd.DataFrame(bundle["latest_market"])
    feat_row = {
        "price_lag1": market_hist[price_col].iloc[-1],
        "price_lag7": market_hist[price_col].iloc[max(0, len(market_hist) - 7)],
        "price_ma7": market_hist[price_col].tail(7).mean(),
        "rainfall_ma7": market_hist["rainfall"].tail(7).mean(),
        "temp_ma7": market_hist["temp_mean"].tail(7).mean(),
        "demand_lag1": market_hist["demand_index"].iloc[-1],
        "day_of_year": datetime.now().timetuple().tm_yday,
        "month": datetime.now().month,
    }
    X_price = pd.DataFrame([{k: feat_row[k] for k in features}])
    price_forecast = bundle[model_key].predict(X_price)[0]
    current_price = float(latest_market[price_col])

    recs = generate_recommendations(
        predicted_risk, price_forecast, current_price,
        float(latest_weather["soil_moisture"]), crop,
    )

    return {
        "location": bundle["location"]["name"],
        "risk": predicted_risk,
        "risk_model_accuracy": round(float(bundle["risk_acc"]) * 100, 1),
        "used_live_sensor_input": used_override,
        "crop": crop,
        "current_price_kes_per_kg": round(current_price, 2),
        "forecast_price_kes_per_kg": round(float(price_forecast), 2),
        "soil_moisture_pct": round(float(latest_weather["soil_moisture"]), 1),
        "ndvi": round(float(ndvi_latest["ndvi"]), 2),
        "vegetation_health": ndvi_latest["vegetation_health"],
        "soil_type": bundle["soil_info"]["type"],
        "recommendations": recs,
        "trained_at": bundle["trained_at"],
    }


def get_weather_history(location_name="nairobi"):
    """Used by the dashboard's Plotly trend chart."""
    bundle = load_bundle(location_name)
    return pd.DataFrame(bundle["latest_weather"])


if __name__ == "__main__":
    import time
    start = time.time()
    for i, (name, (lat, lon)) in enumerate(DEFAULT_LOCATIONS.items(), 1):
        path, bundle = build_and_save_models(lat, lon, name)
        print(f"[{i}/47] Trained & saved: {name} (risk acc={bundle['risk_acc']:.2f})")
    print(f"Done in {time.time() - start:.1f}s")
