import json
from typing import Any, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.config import settings

# Fast, small model and JSON response
_llm = ChatOpenAI(
    model=settings.openai_model,                 # e.g. "gpt-4o-mini"
    temperature=0.2,
    api_key=settings.openai_api_key,
    model_kwargs={"response_format": {"type": "json_object"}},
    timeout=12,                                  # guard against long hangs
    max_retries=1
)

# IMPORTANT: escape literal JSON braces with {{ }}
_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an agriculture advisor for Indian farming contexts. "
     "Be concise, practical, and avoid guarantees. Respond ONLY with valid JSON."),
    ("user",
     """Given these inputs, enrich each crop with fields.

Inputs:
- soil: {soil}
- season: {season}
- month: {month}
- climate: {climate}
- crops: {crops}  # array of items: {{ "crop","duration_days","expected_yield_qpa" }}

Return EXACT JSON (no commentary) with this schema:
{{
  "items": [
    {{
      "crop": "string (must match input)",
      "explanation": "1-2 sentences",
      "best_practices": ["short bullet", "short bullet", "short bullet"],
      "market": {{
        "trend": "rising|steady|falling",
        "last6m": [
          {{ "month": int (1-12), "price": float }},
          {{ "month": int, "price": float }},
          {{ "month": int, "price": float }},
          {{ "month": int, "price": float }},
          {{ "month": int, "price": float }},
          {{ "month": int, "price": float }}
        ]
      }},
      "pest_disease": {{
        "risks": [
          {{ "name": "string", "likelihood": "low|medium|high", "tip": "short actionable" }},
          {{ "name": "string", "likelihood": "low|medium|high", "tip": "short actionable" }}
        ]
      }}
    }}
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
    return json.loads(s or "{}")

def batch_enrich(
    crops: List[Dict[str, Any]],
    soil: str,
    season: str,
    month: int | None,
    climate: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """One OpenAI call that returns enrichment for all crops."""
    msg = _PROMPT.format_messages(
        soil=soil,
        season=season,
        month=month or 6,
        climate=climate or {},
        crops=crops
    )
    try:
        resp = _llm.invoke(msg)
        content = getattr(resp, "content", "") or ""
        data = _safe_json(content)
        items = data.get("items") or []

        # Clamp sizes defensively
        for it in items:
            it["best_practices"] = (it.get("best_practices") or [])[:3]
            # Ensure market structure exists
            it.setdefault("market", {"trend": "steady", "last6m": []})
            it["market"]["last6m"] = (it["market"].get("last6m") or [])[:6]
            it.setdefault("pest_disease", {"risks": []})
            it["pest_disease"]["risks"] = (it["pest_disease"].get("risks") or [])[:3]
        return {"items": items}
    except Exception:
        # Minimal safe fallback for entire batch
        out = []
        for c in crops:
            y0, y1 = c["expected_yield_qpa"]
            out.append({
                "crop": c["crop"],
                "explanation": f"{c['crop'].title()} suits {soil} in {season}. "
                               f"Duration {c['duration_days']} days; expected {y0}–{y1} q/acre.",
                "best_practices": [
                    "Use certified seeds and recommended spacing.",
                    "Apply balanced NPK based on soil test.",
                    "Weed early during the first 3–4 weeks."
                ],
                "market": {
                    "trend": "steady",
                    "last6m": [{"month": i, "price": 3000.0 + 10*i} for i in range(1,7)]
                },
                "pest_disease": {
                    "risks": [
                        {"name":"General pests","likelihood":"medium","tip":"Scout weekly; keep field clean."}
                    ]
                }
            })
        return {"items": out}
