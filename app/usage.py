from datetime import datetime
from bson import ObjectId
from app.db import db
# from app.plans import month_key

def month_key(dt: datetime | None = None) -> str:
    d = dt or datetime.utcnow()
    return f"{d.year:04d}-{d.month:02d}"

async def get_usage(user_id: str) -> int:
    mk = month_key()
    doc = await db.usage.find_one({"userId": ObjectId(user_id), "monthKey": mk})
    # return int(doc["count"]) if doc and "count" in doc else 0
    if not doc:
        return 0
    return int(doc.get("count", 0))

async def increment_usage(user_id: str, inc: int = 1) -> int:
    mk = month_key()
    res = await db.usage.find_one_and_update(
        {"userId": ObjectId(user_id), "monthKey": mk},
        {"$inc": {"count": inc}, "$setOnInsert": {"createdAt": datetime.utcnow()}},
        upsert=True, return_document=True
    )
    # in Motor, return_document=True returns the updated doc
    doc = res or await db.usage.find_one({"userId": ObjectId(user_id), "monthKey": mk})
    # return int(doc["count"]) if doc and "count" in doc else inc
    if not doc:
        return inc
    return int(doc.get("count", inc))
