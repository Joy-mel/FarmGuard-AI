# FarmGuard AI — Full Architecture (v2)

## Directory structure
```
farmguard_v2/
├── api/                      # Component 1: FastAPI backend
│   ├── main.py               #   /predict, /health, /webhook/whatsapp, /api/counties,
│   │                         #   /api/predict/all, /api/history, /refresh
│   ├── schemas.py            #   Pydantic request/response models
│   ├── model_pipeline.py     #   training + prediction for all 47 counties
│   ├── kenya_counties.py     #   47 counties: lat/lon + agro-ecological zone + soil profiles
│   ├── requirements.txt
│   └── models/                #   trained .joblib bundles, one per county
├── dashboard/                # Component 2: Streamlit live dashboard
│   ├── app.py                 #   dark-green themed UI, calls the API over HTTP
│   ├── assets/                 #   drop banner.png / logo.png here (optional)
│   └── requirements.txt
├── whatsapp/                 # Component 3: WhatsApp bot logic
│   └── handler.py             #   message parsing + reply building, provider-agnostic
├── Dockerfile.api
├── Dockerfile.dashboard
└── README.md (this file)
```

The three components are genuinely separable: `dashboard/app.py` only ever
talks to the API over HTTP (never imports model code directly), and
`whatsapp/handler.py` contains pure message-in/reply-out logic with no
Twilio-specific code, so swapping to Meta's WhatsApp Cloud API directly
later only touches `api/main.py`'s webhook glue, not the bot's brain.

## All 47 Kenyan counties
`api/kenya_counties.py` lists every county with a centroid lat/lon and one
of 7 agro-ecological zones (central highlands, lake basin, rift valley,
eastern semi-arid, coast, arid north, southern rangelands). Soil profiles
are assigned per zone, not per county — that's a genuine simplification,
documented in that file, and the honest reason two counties in the same
zone show the same soil type. Swap `ZONE_SOIL_PROFILES` lookups for a real
Kenya Soil Survey / FAO HWSD query before any real agronomic decision
leans on soil guidance specifically.

New endpoint for bulk access: **`GET /api/predict/all?crop=maize`** runs
the prediction for all 47 counties in one call (~2 seconds) — this is
what would back a national map/table view.

---

## Running it locally

**Terminal 1 — API:**
```bash
cd api
pip install -r requirements.txt
python model_pipeline.py        # trains all 47 counties, ~30s
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Dashboard:**
```bash
cd dashboard
pip install -r requirements.txt
export FARMGUARD_API_URL="http://localhost:8000"     # Windows PowerShell: $env:FARMGUARD_API_URL="http://localhost:8000"
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Open `http://localhost:8501` — that's the dashboard talking live to the API.

---

## Opening the dashboard beyond localhost

Three options depending on who needs access and for how long:

### Option A — Same WiFi network (instant, free, no setup)
Since both services are bound to `0.0.0.0` (not just `127.0.0.1`), anyone
on the same network can reach them via your machine's local IP instead of
`localhost`:
```bash
# find your local IP
ipconfig            # Windows: look for "IPv4 Address", e.g. 192.168.1.42
ifconfig            # Mac/Linux
```
Then anyone on the same WiFi opens `http://192.168.1.42:8501` (dashboard)
or `http://192.168.1.42:8000` (API). Nothing to install — this alone
answers "not just my localhost" for anyone in the same room/office.

### Option B — Public internet, temporary (minutes, free, good for demos)
Use `ngrok` to tunnel each port to a public HTTPS URL:
```bash
ngrok http 8501     # dashboard -> https://xxxx.ngrok-free.app
ngrok http 8000      # API, in a second ngrok session -> https://yyyy.ngrok-free.app
```
If you tunnel the API too, point the dashboard at the tunneled API URL:
```bash
export FARMGUARD_API_URL="https://yyyy.ngrok-free.app"
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
Share the dashboard's `ngrok-free.app` link with anyone, anywhere. Free
tier URLs change every restart and your laptop has to stay on — fine for
a demo, not for something you leave running unattended.

### Option C — Public internet, permanent (recommended once past demo stage)
- **Dashboard → Streamlit Community Cloud** (free): push this repo to
  GitHub, go to share.streamlit.io, point it at `dashboard/app.py`, and
  set `FARMGUARD_API_URL` as a secret in its settings. You get a stable
  `yourapp.streamlit.app` URL that's up even when your laptop is off.
- **API → Google Cloud Run** (free tier covers a pilot's traffic):
  ```bash
  gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/farmguard-api -f Dockerfile.api .
  gcloud run deploy farmguard-api \
    --image gcr.io/YOUR_PROJECT_ID/farmguard-api \
    --allow-unauthenticated --region africa-south1 \
    --set-secrets TWILIO_AUTH_TOKEN=twilio-auth-token:latest,REFRESH_SECRET=refresh-secret:latest
  ```
  Then set the Streamlit Cloud secret `FARMGUARD_API_URL` to the Cloud Run
  URL it gives you. The dashboard's `Dockerfile.dashboard` also lets you
  run it on Cloud Run instead of Streamlit Cloud if you'd rather keep
  everything on GCP:
  ```bash
  gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/farmguard-dashboard -f Dockerfile.dashboard .
  gcloud run deploy farmguard-dashboard \
    --image gcr.io/YOUR_PROJECT_ID/farmguard-dashboard \
    --allow-unauthenticated --region africa-south1 \
    --set-env-vars FARMGUARD_API_URL=https://farmguard-api-xxxxx.run.app
  ```

### WhatsApp (any option above)
Point Twilio's webhook at whichever API URL you're running:
```
https://<your-api-url>/webhook/whatsapp
```
Twilio sandbox setup: sign up at twilio.com (free) → Messaging → Try it
out → Send a WhatsApp message → join the sandbox from your phone with the
code shown → paste the webhook URL above into "When a message comes in."

---

## Security (already implemented and tested)

| Threat | Control |
|---|---|
| Forged/unsigned WhatsApp webhook calls | `X-Twilio-Signature` verification via `TWILIO_AUTH_TOKEN`. Set this env var before exposing the webhook publicly — without it the check is skipped with a loud log warning. |
| API/webhook abuse, scraping | Per-IP rate limits (`slowapi`): 20/min `/predict`, 30/min webhook & counties list, 6/hour bulk `/api/predict/all`, 5/hour `/refresh`. |
| Unauthorized model retraining | `/refresh` requires `REFRESH_SECRET`; fails closed (503) if unset, constant-time comparison against timing attacks. |
| Bad input (injection, garbage values) | Pydantic validates every field (ranges, allowed county/crop enums via `field_validator`) — invalid input gets a 422, never silently used. |
| Info disclosure | `/docs`, `/redoc`, `/openapi.json` disabled unless `DEBUG=1`. |
| Clickjacking, MIME sniffing, downgrade | Security headers on every API response (`X-Frame-Options`, `X-Content-Type-Options`, HSTS). |
| Cross-origin abuse | CORS restricted to `ALLOWED_ORIGIN` env var — set to your real dashboard domain in production. |
| Oversized payloads | Requests over ~4KB rejected before processing. |
| Compromised dependency → container root | Both Dockerfiles run as non-root `appuser`. |
| Secrets in source control | Nothing hardcoded — `TWILIO_AUTH_TOKEN`, `REFRESH_SECRET`, `ALLOWED_ORIGIN` all come from environment variables / Secret Manager. |

Set secrets before any public deployment:
```bash
export TWILIO_AUTH_TOKEN="from-twilio-console"
export REFRESH_SECRET="$(openssl rand -hex 32)"
export ALLOWED_ORIGIN="https://your-dashboard-domain"
```

## What's simulated vs. real
- **Real:** weather comes from the Open-Meteo Archive API for each
  county's actual coordinates (falls back to a synthetic-but-seasonal
  series only if that API is unreachable).
- **Simulated:** NDVI, market prices, and per-county soil detail (beyond
  the 7-zone grouping) are realistic placeholders, not live satellite or
  market feeds. See inline comments in `model_pipeline.py` and
  `kenya_counties.py` for exactly where, and what to swap in for
  production (Sentinel Hub/Earth Engine for NDVI, Kenya Ministry of
  Agriculture bulletins for prices, Kenya Soil Survey for soil).
