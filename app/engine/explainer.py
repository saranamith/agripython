from typing import Dict
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from app.config import settings

_prompt = PromptTemplate.from_template(
    "You are an agriculture advisor. Given soil='{soil}', season='{season}', crop='{crop}', "
    "write a brief, practical justification (max 2 sentences). Include duration {duration_days} days "
    "and expected yield {yield_min}-{yield_max} q/acre. Avoid guarantees and keep it simple."
)

_llm = ChatOpenAI(model=settings.openai_model, temperature=0.2, api_key=settings.openai_api_key)

def explain(item: Dict, soil: str, season: str) -> str:
    y0, y1 = item["expected_yield_qpa"]
    try:
        chain = _prompt | _llm
        resp = chain.invoke({
            "soil": soil,
            "season": season,
            "crop": item["crop"],
            "duration_days": item["duration_days"],
            "yield_min": y0,
            "yield_max": y1
        })
        text = getattr(resp, "content", None) or (resp if isinstance(resp, str) else "")
        text = (text or "").strip()
        if text:
            return text
    except Exception:
        pass
    # Fallback
    return (f"{item['crop'].title()} suits {soil} soil in {season}. "
            f"Duration {item['duration_days']} days; expected {y0}–{y1} q/acre.")
