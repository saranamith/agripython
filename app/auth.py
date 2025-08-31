from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from app.db import db
from app.security import create_token, current_user
from app.plans import ensure_free_on_register, subscription_summary
from app.config import settings
import httpx

router = APIRouter()

# ---------- DTOs ----------
class RegisterBody(BaseModel):
    name: str
    email: EmailStr

class LoginBody(BaseModel):
    email: EmailStr

class GoogleBody(BaseModel):
    id_token: str  # from Google Sign-In on frontend

# ---------- Register (name + email) ----------
@router.post("/register")
async def register(body: RegisterBody):
    existing = await db.users.find_one({"email": body.email})
    if existing:
        # idempotent: return token for existing user
        uid = str(existing["_id"])
        return {"token": create_token(uid), "user": {"id": uid, "name": existing.get("name"), "email": existing["email"]},"subscription": await subscription_summary(uid)}
    doc = {"name": body.name, "email": body.email}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    await ensure_free_on_register(uid)
    return {"token": create_token(uid), "user": {"id": uid, "name": body.name, "email": body.email},"subscription": await subscription_summary(uid)}


# ---------- Login (email only) ----------
@router.post("/login")
async def login(body: LoginBody):
    user = await db.users.find_one({"email": body.email})
    if not user:
        if settings.dev_passwordless:
            # DEV convenience: auto-create user if not exists
            res = await db.users.insert_one({"email": body.email, "name": body.email.split("@")[0]})
            uid = str(res.inserted_id)
            return {"token": create_token(uid), "user": {"id": uid, "name": body.email.split("@")[0], "email": body.email}}
        raise HTTPException(404, "User not found")
    uid = str(user["_id"])
    return {"token": create_token(uid), "user": {"id": uid, "name": user.get("name"), "email": user["email"]}}


# ---------- Google sign-in / sign-up ----------
@router.post("/google")
async def google(body: GoogleBody):
    # Verify with Google tokeninfo
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.id_token})
    if r.status_code != 200:
        raise HTTPException(401, "Invalid Google ID token")
    data = r.json()
    aud = data.get("aud")
    if settings.google_audience and aud != settings.google_audience:
        raise HTTPException(401, "Audience mismatch")
    email = data.get("email")
    name = data.get("name") or (email.split("@")[0] if email else "User")
    if not email:
        raise HTTPException(400, "Google token missing email")

    user = await db.users.find_one({"email": email})
    if not user:
        res = await db.users.insert_one({"email": email, "name": name, "google_sub": data.get("sub")})
        uid = str(res.inserted_id)
        await ensure_free_on_register(uid)
        return {"token": create_token(uid), "user": {"id": uid, "name": name, "email": email},"subscription": await subscription_summary(uid)}
    uid = str(user["_id"])
    # update name on first Google login if missing
    if not user.get("name") and name:
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"name": name}})
    return {"token": create_token(uid), "user": {"id": uid, "name": user.get("name") or name, "email": email},"subscription": await subscription_summary(uid)}

# ---------- Me ----------
@router.get("/me")
async def me(user = Depends(current_user)):
    return {"id": user["id"], "name": user.get("name"), "email": user["email"]}
