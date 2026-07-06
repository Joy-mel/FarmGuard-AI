"""
FarmGuard AI - API Layer (FastAPI)
====================================
Endpoints:
  POST /predict              - accepts sensor/environmental data, returns AI prediction
  GET  /health               - system health check
  POST /webhook/whatsapp     - Twilio WhatsApp webhook (logic in whatsapp/handler.py)
  GET  /api/counties         - list all 47 Kenyan counties FarmGuard covers
  GET  /api/predict/all      - bulk prediction for EVERY county at once
  POST /refresh              - admin: retrain all counties (Cloud Scheduler)

Run from the project root:
    cd farmguard_v2/api
    uvicorn main:app --reload --port 8000 --host 0.0.0.0
"""

import os
import sys
import html
import logging

from fastapi import FastAPI, Form, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from model_pipeline import predict_for_farmer, build_and_save_models, get_weather_history, DEFAULT_LOCATIONS, MODEL_DIR
from schemas import SensorReading, PredictionResponse, CountySummary, HealthResponse, ALLOWED_LOCATIONS, ALLOWED_CROPS
from kenya_counties import KENYA_COUNTIES

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "whatsapp"))
from handler import handle_incoming_message, verify_twilio_signature  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("farmguard-api")

DEBUG = os.environ.get("DEBUG", "0") == "1"
REFRESH_SECRET = os.environ.get("REFRESH_SECRET")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
MAX_BODY_BYTES = 4_000

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="FarmGuard AI API",
    description="Climate risk & crop price predictions for all 47 Kenyan counties",
    version="2.0.0",
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN] if ALLOWED_ORIGIN != "*" else ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Payload too large"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)


def _to_prediction_response(result: dict) -> PredictionResponse:
    change_pct = ((result["forecast_price_kes_per_kg"] - result["current_price_kes_per_kg"])
                  / result["current_price_kes_per_kg"]) * 100
    return PredictionResponse(
        location=result["location"], crop=result["crop"],
        climate_risk=result["risk"], risk_model_accuracy_pct=result["risk_model_accuracy"],
        current_price_kes_per_kg=result["current_price_kes_per_kg"],
        forecast_price_kes_per_kg=result["forecast_price_kes_per_kg"],
        price_change_pct=round(change_pct, 1),
        soil_moisture_pct=result["soil_moisture_pct"], ndvi=result["ndvi"],
        vegetation_health=result["vegetation_health"], soil_type=result["soil_type"],
        recommendations=result["recommendations"], trained_at=result["trained_at"],
        used_live_sensor_input=result["used_live_sensor_input"],
    )


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------

@app.post("/predict", response_model=PredictionResponse)
@limiter.limit("20/minute")
def predict(request: Request, reading: SensorReading):
    try:
        overrides = {
            "temperature_c": reading.temperature_c, "rainfall_mm": reading.rainfall_mm,
            "soil_moisture_pct": reading.soil_moisture_pct, "humidity_pct": reading.humidity_pct,
            "evapotranspiration_mm": reading.evapotranspiration_mm,
        }
        overrides = {k: v for k, v in overrides.items() if v is not None}
        result = predict_for_farmer(reading.location, reading.crop, overrides)
    except Exception:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail="Prediction failed. Please try again.")
    return _to_prediction_response(result)


# ---------------------------------------------------------------------------
# GET /api/counties  and  GET /api/predict/all  (every county in one call)
# ---------------------------------------------------------------------------

@app.get("/api/counties")
@limiter.limit("30/minute")
def list_counties(request: Request):
    return {
        "total": len(KENYA_COUNTIES),
        "counties": [
            {"name": name, "lat": lat, "lon": lon, "zone": zone}
            for name, (lat, lon, zone) in sorted(KENYA_COUNTIES.items())
        ],
    }


@app.get("/api/predict/all", response_model=list[CountySummary])
@limiter.limit("6/hour")
def predict_all_counties(request: Request, crop: str = Query("maize")):
    """Bulk endpoint: fetches a prediction for EVERY one of Kenya's 47
    counties in a single call. Rate-limited tighter than /predict since
    each call does 47x the work - suitable for populating the dashboard's
    national map/table view, not for a per-message WhatsApp reply."""
    crop = crop.lower().strip()
    if crop not in ALLOWED_CROPS:
        raise HTTPException(status_code=422, detail=f"crop must be one of {ALLOWED_CROPS}")

    results = []
    for name in KENYA_COUNTIES:
        try:
            r = predict_for_farmer(name, crop)
            results.append(CountySummary(
                location=r["location"], climate_risk=r["risk"],
                soil_moisture_pct=r["soil_moisture_pct"], soil_type=r["soil_type"],
                current_price_kes_per_kg=r["current_price_kes_per_kg"],
                forecast_price_kes_per_kg=r["forecast_price_kes_per_kg"],
            ))
        except Exception:
            logger.exception(f"Prediction failed for {name}, skipping")
    return results


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/api/history")
@limiter.limit("30/minute")
def county_history(request: Request, location: str = Query("nairobi")):
    """Real 14-day weather/soil-moisture window backing the dashboard's
    trend chart - not simulated, pulled from the same data the models
    were trained on."""
    location = location.lower().strip().replace(" ", "_").replace("-", "_")
    if location not in ALLOWED_LOCATIONS:
        raise HTTPException(status_code=422, detail="Unknown county")
    df = get_weather_history(location)
    return {
        "location": location,
        "days": df["date"].astype(str).tolist(),
        "temp_mean": df["temp_mean"].round(1).tolist(),
        "rainfall": df["rainfall"].round(1).tolist(),
        "soil_moisture": df["soil_moisture"].round(1).tolist(),
    }


@app.get("/health", response_model=HealthResponse)
def health():
    loaded = sum(1 for loc in DEFAULT_LOCATIONS if os.path.exists(os.path.join(MODEL_DIR, f"{loc}.joblib")))
    return HealthResponse(status="ok", total_counties=len(KENYA_COUNTIES), models_loaded=loaded)


# ---------------------------------------------------------------------------
# POST /webhook/whatsapp
# ---------------------------------------------------------------------------

@app.post("/webhook/whatsapp", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def whatsapp_webhook(request: Request, Body: str = Form("")):
    form = await request.form()
    signature = request.headers.get("X-Twilio-Signature", "")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    url = str(request.url.replace(scheme=proto))

    if not verify_twilio_signature(url, dict(form), signature, TWILIO_AUTH_TOKEN):
        logger.warning("Rejected /webhook/whatsapp POST with invalid Twilio signature.")
        raise HTTPException(status_code=403, detail="Invalid signature")

    reply = handle_incoming_message(Body)
    twiml = f"<Response><Message>{html.escape(reply)}</Message></Response>"
    return PlainTextResponse(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# POST /refresh (admin)
# ---------------------------------------------------------------------------

@app.post("/refresh")
@limiter.limit("5/hour")
def refresh_models(request: Request, secret: str = Query("")):
    import hmac
    if not REFRESH_SECRET:
        raise HTTPException(status_code=503, detail="REFRESH_SECRET not configured")
    if not hmac.compare_digest(secret, REFRESH_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    results = {}
    for name, (lat, lon) in DEFAULT_LOCATIONS.items():
        _, bundle = build_and_save_models(lat, lon, name)
        results[name] = {"risk_accuracy": round(float(bundle["risk_acc"]) * 100, 1)}
    return {"status": "refreshed", "counties_trained": len(results)}
