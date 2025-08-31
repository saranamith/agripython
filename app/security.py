import time, jwt
from fastapi import Header, HTTPException
from bson import ObjectId
from app.config import settings
from app.db import db

def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + 60 * settings.jwt_expire_min}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

async def current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Invalid token")
    uid = payload.get("sub")
    user = await db.users.find_one({"_id": ObjectId(uid)})
    if not user:
        raise HTTPException(401, "User not found")
    # normalize id to string for responses
    user["id"] = str(user["_id"])
    return user
