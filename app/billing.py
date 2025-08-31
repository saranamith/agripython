import hmac, hashlib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Form
from pydantic import BaseModel
from bson import ObjectId
from fastapi.responses import RedirectResponse, JSONResponse
import razorpay
from urllib.parse import quote

from app.config import settings
from app.security import current_user
from app.db import db
from app.plans import PLANS, PlanId, activate_subscription,subscription_summary

router = APIRouter()

class CreateOrderBody(BaseModel):
    planId: PlanId

@router.get("/plans")
def list_plans():
    return {
        "plans": [
            {
                "id": p["id"],
                "name": p["name"],
                "price_inr": p["price_inr"],
                "monthly_quota": p["monthly_quota"],
                "features": p["features"],
            }
            for p in PLANS.values()
        ]
    }


@router.get("/me/subscription")
async def me_subscription(user=Depends(current_user)):
    return await subscription_summary(user["id"])


@router.post("/create-order")
async def create_order(body: CreateOrderBody, user=Depends(current_user)):
    plan = PLANS.get(body.planId)
    if not plan:
        raise HTTPException(400, "Invalid planId")

    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(500, "Razorpay keys not configured")

    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    amount_paise = int(plan["price_inr"] * 100)

    # Tie order to user via receipt (userId|planId|ts)
    receipt = f"{user['id']}|{plan['id']}|{int(datetime.utcnow().timestamp())}"
    order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1
    })

    # Store order mapping (include receipt for later use)
    await db.orders.insert_one({
        "order_id": order["id"],
        "userId": ObjectId(user["id"]),
        "planId": plan["id"],
        "receipt": receipt,                                  # ✅ store receipt
        "amount": amount_paise,
        "currency": "INR",
        "status": order.get("status", "created"),
        "createdAt": datetime.utcnow(),
    })

    # Frontend should open Razorpay Checkout and set callback_url to /billing/verify
    return {
        "key_id": settings.razorpay_key_id,
        "order": order
    }

# ---------------------------
# Redirect/Callback verifier
# ---------------------------
@router.post("/verify")
async def verify_payment(
    razorpay_payment_id: str = Form(...),
    razorpay_order_id: str = Form(...),
    razorpay_signature: str = Form(...)
):
    """
    This endpoint is used as Razorpay Checkout callback_url.
    Razorpay will POST form fields:
      - razorpay_payment_id
      - razorpay_order_id
      - razorpay_signature
    We verify the signature and activate the plan.
    """
    print("verification method called")
    if not settings.razorpay_key_secret:
        raise HTTPException(500, "Razorpay secret not configured")

    # 1) Verify signature (order_id|payment_id with key_secret)
    body = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected = hmac.new(settings.razorpay_key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, razorpay_signature):
        url = f"{settings.frontend_base_url}/payment/failure?reason={quote('invalid_signature')}"
        return RedirectResponse(url, status_code=303)

    # 2) Idempotency: if we already marked this order paid, return success
    existing = await db.orders.find_one({"order_id": razorpay_order_id})
    user_id = str(existing["userId"]) if existing and existing.get("userId") else None
    plan_id = existing["planId"] if existing else None
    receipt = existing.get("receipt") if existing else None
    # if existing and existing.get("status") == "paid":
    #     return {"ok": True, "already_paid": True, "planId": existing.get("planId")}

    # 3) Resolve user/plan: from our order doc (preferred) or, as fallback, fetch from Razorpay
    # user_id = None
    # plan_id = None
    # if existing:
    #     user_id = str(existing["userId"]) if existing.get("userId") else None
    #     plan_id = existing.get("planId")

    if not user_id or not plan_id:
        try:
            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            rzp_order = client.order.fetch(razorpay_order_id)
            receipt = rzp_order.get("receipt", "")
            if receipt and "|" in receipt:
                parts = receipt.split("|")
                # if len(parts) >= 2:
                user_id = user_id or parts[0]
                plan_id = plan_id or parts[1]
        except Exception:
            url = f"{settings.frontend_base_url}/payment/failure?reason={quote('order_not_found')}"
            return RedirectResponse(url, status_code=303)

    if not (user_id and plan_id and plan_id in PLANS):
        url = f"{settings.frontend_base_url}/payment/failure?reason={quote('plan_or_user_missing')}"
        return RedirectResponse(url, status_code=303)


    # 4) Activate subscription (30 days)
    await activate_subscription(user_id, plan_id)

    # 5) Mark order paid (idempotent upsert)
    await db.orders.update_one(
        {"order_id": razorpay_order_id},
        {"$set": {
            "payment_id": razorpay_payment_id,
            "status": "paid",
            "updatedAt": datetime.utcnow()
        },
         "$setOnInsert": {"createdAt": datetime.utcnow()}},
        upsert=True
    )
    success_url = f"{settings.frontend_base_url}/payment/success?planId={plan_id}"
    return RedirectResponse(success_url, status_code=303)
    # return {"ok": True, "planId": plan_id}

# ---------------------------
# (Optional) Webhook (kept, with small fix)
# ---------------------------
@router.post("/webhook")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(None)):
    if not settings.razorpay_webhook_secret:
        raise HTTPException(500, "Webhook secret not configured")

    raw = await request.body()
    digest = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()

    # ✅ FIX: must be *not* compare_digest to reject invalid signatures
    if not x_razorpay_signature or not hmac.compare_digest(digest, x_razorpay_signature):
        raise HTTPException(401, "Invalid signature")

    payload = await request.json()
    event = payload.get("event")
    if event not in {"payment.captured", "order.paid"}:
        return {"ok": True}

    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
    order_entity   = payload.get("payload", {}).get("order",   {}).get("entity", {}) or {}

    order_id   = payment_entity.get("order_id") or order_entity.get("id")
    payment_id = payment_entity.get("id")
    amount     = payment_entity.get("amount") or order_entity.get("amount")
    currency   = payment_entity.get("currency") or order_entity.get("currency") or "INR"

    if not order_id:
        return {"ok": True}

    existing = await db.orders.find_one({"order_id": order_id})
    if existing and existing.get("status") == "paid":
        return {"ok": True}

    user_id = None
    plan_id = None
    receipt = existing.get("receipt") if existing else None

    if not receipt:
        try:
            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            rzp_order = client.order.fetch(order_id)
            receipt   = rzp_order.get("receipt")
            amount    = amount or rzp_order.get("amount")
            currency  = currency or rzp_order.get("currency", "INR")
        except Exception:
            return {"ok": True}

    if receipt and "|" in receipt:
        parts = receipt.split("|")
        if len(parts) >= 2:
            user_id = str(existing["userId"]) if (existing and existing.get("userId")) else parts[0]
            plan_id = existing.get("planId") if (existing and existing.get("planId")) else parts[1]

    if not user_id or not plan_id:
        return {"ok": True}

    plan = PLANS.get(plan_id)
    if not plan:
        return {"ok": True}

    expected = int(plan["price_inr"] * 100)
    if expected > 0 and isinstance(amount, int) and currency == "INR":
        if abs(amount - expected) > 50:
            await db.orders.update_one(
                {"order_id": order_id},
                {"$set": {
                    "status": "mismatch",
                    "amount": amount,
                    "currency": currency,
                    "updatedAt": datetime.utcnow()
                }},
                upsert=True,
            )
            return {"ok": True}

    await activate_subscription(user_id, plan_id)

    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "order_id": order_id,
            "payment_id": payment_id,
            "userId": ObjectId(user_id),
            "planId": plan_id,
            "receipt": receipt,
            "amount": amount,
            "currency": currency,
            "status": "paid",
            "updatedAt": datetime.utcnow()
        },
         "$setOnInsert": {"createdAt": datetime.utcnow()}},
        upsert=True
    )

    return {"ok": True}
