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

# NOTE: All literal JSON braces are doubled {{ ... }} to escape them.
_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an agriculture advisor for Indian farming contexts. "
     "Be practical, concise, and avoid guarantees. Use simple language. "
     "Return STRICT JSON ONLY matching the schema."),
    ("user",
     """Provide structured guidance for a crop recommendation.

Input:
- crop: {crop}
- soil: {soil}
- season: {season}
- climate: {climate}   # may include tempC, rain_mm

Return JSON with this exact schema (no extra fields, no commentary):
{{
  "explanation": "string, 1-2 sentences plain text",
  "best_practices": ["string (short bullet)", "string", "string"],
  "market": {{ "trend": "rising|steady|falling" }},
  "pest_disease": {{
    "risks": [
      {{ "name": "string", "likelihood": "low|medium|high", "tip": "string (short actionable)" }}
    ]
  }}
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

def llm_enrich(
    item: Dict[str, Any],
    soil: str,
    season: str,
    climate: Dict[str, Any] | None
) -> Dict[str, Any]:
    climate_in = climate or {}
    msg = _PROMPT.format_messages(
        crop=item["crop"],
        soil=soil,
        season=season,
        climate=climate_in
    )
    try:
        resp = _llm.invoke(msg)
        content = getattr(resp, "content", "") or ""
        data = _safe_json(content)

        expl = (data.get("explanation") or "").strip()
        bp = (data.get("best_practices") or [])[:3]
        market = data.get("market") or {}
        trend = market.get("trend") if market else None
        pests = data.get("pest_disease") or {}
        risks = (pests.get("risks") or [])[:3]

        return {
            "explanation": expl or f"{item['crop'].title()} suits {soil} soil in {season}.",
            "best_practices": bp or [
                "Use certified seeds and recommended spacing.",
                "Apply balanced NPK based on soil test.",
                "Weed early during the first 3–4 weeks."
            ],
            "market_trend": trend if trend in ("rising","steady","falling") else "steady",
            "pest_risks": risks or [
                {"name": "General pests", "likelihood": "medium", "tip": "Scout weekly; keep field clean."}
            ]
        }
    except Exception:
        y0, y1 = item["expected_yield_qpa"]
        return {
            "explanation": (f"{item['crop'].title()} suits {soil} soil in {season}. "
                            f"Duration {item['duration_days']} days; expected {y0}–{y1} q/acre."),
            "best_practices": [
                "Use certified seeds and recommended spacing.",
                "Apply balanced NPK based on soil test.",
                "Weed early during the first 3–4 weeks."
            ],
            "market_trend": "steady",
            "pest_risks": [
                {"name": "General pests", "likelihood": "medium", "tip": "Scout weekly; keep field clean."}
            ],
        }
