from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import setup_mongo
from app.auth import router as auth_router
from app.schema import RecommendRequest, RecommendResponse
from app.engine.scorer import score, to_items
from app.engine.explainer import explain 
from app.engine.llm_enricher import llm_enrich
from app.engine.market import get_market_info
from app.engine.llm_batch import batch_enrich
from app.history import router as history_router
from datetime import datetime
from fastapi import Depends,HTTPException
from app.security import current_user
from bson import ObjectId
from app.db import db
from app.billing import router as billing_router
from app.plans import get_subscription
from app.usage import get_usage, increment_usage

app = FastAPI(title="Ideal Crop Suggester - Engine (OpenAI-enriched)", version="0.0.3")
app.state.settings = settings
setup_mongo(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

@app.get("/health")
def health():
    return {"ok": True}

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(history_router, prefix="/history", tags=["History"])
app.include_router(billing_router, prefix="/billing", tags=["Billing"])

@app.post("/recommend", response_model=RecommendResponse)
async def recommend(body: RecommendRequest,user=Depends(current_user)):
    sub = await get_subscription(user["id"])
    used = await get_usage(user["id"])
    if used >= sub["monthly_quota"]:
        raise HTTPException(402, detail="Quota exceeded. Upgrade your plan.")
    
    climate = body.climate.model_dump() if body.climate else None
    ranked = score(body.soilType, body.season, climate)
    base_items = to_items(ranked)[:3]

    crop_min = [
        {
            "crop": it["crop"],
            "duration_days": it["duration_days"],
            "expected_yield_qpa": it["expected_yield_qpa"]
        }
        for it in base_items
    ]

    enriched = batch_enrich(
        crops=crop_min,
        soil=body.soilType,
        season=body.season,
        month=body.month,
        climate=climate
    )["items"]

    enrich_by_crop = {e["crop"]: e for e in enriched}

    final = []

    for it in base_items:
        e = enrich_by_crop.get(it["crop"], {})
        final.append({
            **it,
            "explanation": e.get("explanation", ""),
            "best_practices": e.get("best_practices", []),
            "market": e.get("market", {"trend":"steady","last6m":[]}),
            "pest_disease": e.get("pest_disease", {"risks":[]}),
        })

    await increment_usage(user["id"], 1)
    
    doc = {
        "userId": ObjectId(user["id"]),
        "request": {
            "soilType": body.soilType,
            "season": body.season,
            "month": body.month,
            "climate": climate or {}
        },
        "items": final,
        "createdAt": datetime.utcnow().isoformat()
    }
    await db.histories.insert_one(doc)

    return {"items": final}
