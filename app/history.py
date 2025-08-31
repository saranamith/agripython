from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from bson import ObjectId
from app.db import db
from app.security import current_user

router = APIRouter()

def _serialize(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc["_id"] = str(doc["_id"])
    if "userId" in doc:
        doc["userId"] = str(doc["userId"])
    return doc

@router.get("/", summary="List my history")
async def list_history(
    user = Depends(current_user),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    cursor = db.histories.find({"userId": ObjectId(user["id"])}).sort("createdAt", -1).skip(skip).limit(limit)
    items = [_serialize(x) async for x in cursor]
    return {"items": items}

@router.get("/{history_id}", summary="Get one history item")
async def get_history(history_id: str, user = Depends(current_user)):
    try:
        oid = ObjectId(history_id)
    except Exception:
        raise HTTPException(400, "Invalid history id")
    doc = await db.histories.find_one({"_id": oid, "userId": ObjectId(user["id"])})
    if not doc:
        raise HTTPException(404, "Not found")
    return _serialize(doc)
