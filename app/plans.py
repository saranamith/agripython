# app/plans.py
from datetime import datetime, timedelta
from typing import Literal, Optional, Dict, Any
from bson import ObjectId
from app.db import db
from app.usage import get_usage

PlanId = Literal["free","lite","pro"]

PLANS: Dict[PlanId, Dict[str, Any]] = {
    "free": {"id":"free","name":"Free","price_inr":0,"monthly_quota":1,  # 1 trial credit
             "features":{"market":False,"pest":False}},
    "lite": {"id":"lite","name":"Lite","price_inr":199,"monthly_quota":50,
             "features":{"market":True,"pest":True}},
    "pro":  {"id":"pro","name":"Pro","price_inr":499,"monthly_quota":500,
             "features":{"market":True,"pest":True}},
}

def month_key(dt: Optional[datetime]=None) -> str:
    d = dt or datetime.utcnow()
    return f"{d.year:04d}-{d.month:02d}"

async def ensure_free_on_register(user_id: str):
    """Create a Free subscription doc on first registration (idempotent)."""
    now = datetime.utcnow()
    await db.subscriptions.update_one(
        {"userId": ObjectId(user_id)},
        {"$setOnInsert": {
            "planId": "free",
            "active": True,
            "validTill": None,   # unlimited until upgrade; quota enforced monthly
            "createdAt": now,
            "updatedAt": now
        }},
        upsert=True
    )

async def get_subscription(user_id: str) -> Dict[str, Any]:
    sub = await db.subscriptions.find_one({"userId": ObjectId(user_id)})
    now = datetime.utcnow()
    if not sub or not sub.get("active"):
        return {"planId":"free","active":True,"validTill":None,
                "features":PLANS["free"]["features"],"monthly_quota":PLANS["free"]["monthly_quota"]}
    pid: PlanId = sub.get("planId","free")  # type: ignore
    plan = PLANS.get(pid, PLANS["free"])
    return {"planId": pid, "active":True, "validTill": sub.get("validTill"),
            "features": plan["features"], "monthly_quota": plan["monthly_quota"]}

async def activate_subscription(user_id: str, plan_id: PlanId, days: int = 30):
    now = datetime.utcnow()
    valid_till = now + timedelta(days=days)
    await db.subscriptions.update_one(
        {"userId": ObjectId(user_id)},
        {"$set": {"planId": plan_id, "active": True, "validTill": valid_till, "updatedAt": now},
         "$setOnInsert": {"createdAt": now}},
        upsert=True
    )

async def subscription_summary(user_id: str) -> Dict[str, Any]:
    """Pack plan + usage into one dict for responses."""
    sub = await get_subscription(user_id)
    used = await get_usage(user_id)
    remaining = max(sub["monthly_quota"] - used, 0)
    return {
        "planId": sub["planId"],
        "monthly_quota": sub["monthly_quota"],
        "used": used,
        "remaining": remaining,
        "features": sub["features"],
        "validTill": sub.get("validTill"),
    }
