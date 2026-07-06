"""
FarmGuard AI - API Schemas
===========================
Pydantic models for request validation and response typing.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from kenya_counties import KENYA_COUNTIES

ALLOWED_LOCATIONS = tuple(KENYA_COUNTIES.keys())
ALLOWED_CROPS = ("maize", "beans")


class SensorReading(BaseModel):
    """Raw sensor/environmental input. All fields optional except location
    and crop - any field left out is filled in from that county's latest
    trained-model weather data, so this endpoint works both for a farmer
    with a real IoT sensor and one who just wants a county-level forecast."""

    location: str = Field("nairobi", description=f"One of {len(ALLOWED_LOCATIONS)} Kenyan counties, e.g. 'kisumu'")
    crop: str = Field("maize", description="One of: " + ", ".join(ALLOWED_CROPS))

    temperature_c: Optional[float] = Field(None, ge=-10, le=55, description="Ambient temperature, °C")
    rainfall_mm: Optional[float] = Field(None, ge=0, le=500, description="Rainfall, mm/day")
    soil_moisture_pct: Optional[float] = Field(None, ge=0, le=100, description="Soil moisture, %")
    humidity_pct: Optional[float] = Field(None, ge=0, le=100, description="Relative humidity, %")
    evapotranspiration_mm: Optional[float] = Field(None, ge=0, le=20, description="ET0, mm/day")

    @field_validator("location")
    @classmethod
    def validate_location(cls, v):
        v = v.lower().strip().replace(" ", "_").replace("-", "_")
        if v not in ALLOWED_LOCATIONS:
            raise ValueError(f"location must be one of Kenya's 47 counties, e.g. {ALLOWED_LOCATIONS[:5]}...")
        return v

    @field_validator("crop")
    @classmethod
    def validate_crop(cls, v):
        v = v.lower().strip()
        if v not in ALLOWED_CROPS:
            raise ValueError(f"crop must be one of {ALLOWED_CROPS}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "location": "kisumu",
                "crop": "maize",
                "temperature_c": 29.5,
                "rainfall_mm": 1.2,
                "soil_moisture_pct": 24.0,
                "humidity_pct": 55.0,
                "evapotranspiration_mm": 5.1,
            }
        }


class PredictionResponse(BaseModel):
    location: str
    crop: str
    climate_risk: str = Field(..., description="drought | flood | heat_stress | normal")
    risk_model_accuracy_pct: float
    current_price_kes_per_kg: float
    forecast_price_kes_per_kg: float
    price_change_pct: float
    soil_moisture_pct: float
    ndvi: float
    vegetation_health: str
    soil_type: str
    recommendations: List[str]
    trained_at: str
    used_live_sensor_input: bool


class CountySummary(BaseModel):
    location: str
    climate_risk: str
    soil_moisture_pct: float
    soil_type: str
    current_price_kes_per_kg: float
    forecast_price_kes_per_kg: float


class HealthResponse(BaseModel):
    status: str
    total_counties: int
    models_loaded: int


class ErrorResponse(BaseModel):
    detail: str
