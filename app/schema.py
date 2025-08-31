from pydantic import BaseModel, Field
from typing import Literal, Optional, Tuple, List, Dict

Soil = Literal["clay","sandy","loamy","black","silt","peat","chalk"]
Season = Literal["kharif","rabi","zaid"]

class Location(BaseModel):
    lat: float
    lng: float

class Climate(BaseModel):
    tempC: Optional[float] = None
    humidity: Optional[float] = None
    rain_mm: Optional[float] = None

class RecommendRequest(BaseModel):
    soilType: Soil
    season: Season
    month: Optional[int] = Field(default=None, ge=1, le=12)
    location: Optional[Location] = None
    climate: Optional[Climate] = None

# ✨ NEW types for market & pests
class MarketPoint(BaseModel):
    month: int
    price: float

class MarketInfo(BaseModel):
    trend: Literal["rising","steady","falling"]
    last6m: List[MarketPoint]

class RiskItem(BaseModel):
    name: str
    likelihood: Literal["low","medium","high"]
    tip: str

class PestDisease(BaseModel):
    risks: List[RiskItem]

class CropItem(BaseModel):
    crop: str
    fit_score: float
    duration_days: int
    expected_yield_qpa: Tuple[float, float]
    explanation: str
    # ✨ include the new fields
    best_practices: List[str]
    market: MarketInfo
    pest_disease: PestDisease

class RecommendResponse(BaseModel):
    items: List[CropItem]
