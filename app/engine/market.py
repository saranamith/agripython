import json
from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings

_llm = ChatOpenAI(
    model=settings.openai_model,
    temperature=0.2,
    api_key=settings.openai_api_key,
)

# Escape all literal JSON braces with doubled {{ }}
_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an agricultural economist. "
     "Be practical and concise. Respond ONLY with JSON, no commentary. "
     "Prices should be plausible INR/quintal values (typical mandis), not extremes. "
     "Return exactly in the schema given."),
    ("user",
     """Provide market analysis for the given crop.

Input:
- crop: {crop}
- season: {season}
- month: {month}

Return JSON:
{{
  "trend": "rising|steady|falling",
  "last6m": [
    {{ "month": int (1-12), "price": float }},
    {{ "month": int, "price": float }},
    {{ "month": int, "price": float }},
    {{ "month": int, "price": float }},
    {{ "month": int, "price": float }},
    {{ "month": int, "price": float }}
  ]
}}"""
    )
])

def _safe_json(s: str) -> Dict[str, Any]:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    return json.loads(s)

def get_market_info(crop: str, season: str, month: int | None) -> Dict[str, Any]:
    try:
        msg = _PROMPT.format_messages(
            crop=crop,
            season=season,
            month=month or 6
        )
        resp = _llm.invoke(msg)
        content = getattr(resp, "content", "") or ""
        data = _safe_json(content)

        trend = data.get("trend") or "steady"
        last6m = data.get("last6m") or []
        # Optional: light validation – keep exactly 6 points
        last6m = last6m[:6]
        return {"trend": trend, "last6m": last6m}
    except Exception:
        # Safe fallback
        return {
            "trend": "steady",
            "last6m": [{"month": i, "price": 3000.0 + i*10} for i in range(1, 7)]
        }
