from typing import Dict, List, Tuple
from .crops import CROPS

def score(soil: str, season: str, climate: Dict | None = None) -> List[Tuple[dict, float]]:
    out: List[Tuple[dict, float]] = []
    for c in CROPS:
        soil_fit = c["soils"].get(soil, 0.35)
        season_fit = c["seasons"].get(season, 0.35)
        s = 0.5 * (soil_fit + season_fit)

        if climate:
            temp = climate.get("tempC")
            rain = climate.get("rain_mm")
            if c["crop"] == "paddy" and rain is not None:
                s += 0.05 if rain >= 50 else -0.03
            if c["crop"] == "wheat" and temp is not None:
                s += 0.04 if 10 <= temp <= 25 else -0.02

        s = max(0.0, min(1.0, s))
        out.append((c, s))

    out.sort(key=lambda x: x[1], reverse=True)
    return out

def to_items(scored: List[Tuple[dict, float]]) -> List[dict]:
    return [{
        "crop": c["crop"],
        "fit_score": round(fit, 2),
        "duration_days": c["duration"],
        "expected_yield_qpa": c["yield"],
    } for c, fit in scored[:5]]
