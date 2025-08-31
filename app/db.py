# app/db.py
from typing import Optional
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

class DB:
    client: Optional[AsyncIOMotorClient] = None
    database = None
    users = None
    histories = None
    subscriptions = None
    orders = None
    usage = None

db = DB()

async def ensure_indexes():
    # unique email index for users collection
    await db.users.create_index("email", unique=True, name="uniq_email")
    await db.histories.create_index([("userId", 1), ("createdAt", -1)], name="user_created_idx")
    await db.subscriptions.create_index("userId", unique=True, name="uniq_sub_user")
    await db.orders.create_index("order_id", unique=True, name="uniq_order_id")
    await db.usage.create_index([("userId", 1), ("monthKey", 1)], unique=True, name="uniq_usage_month")

def setup_mongo(app: FastAPI):
    @app.on_event("startup")
    async def _startup():
        if not settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI is not set. Add it to .env")

        client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=8000,
            uuidRepresentation="standard",
        )
        db.client = client

        # If DB name present in URI it’s used; otherwise fall back explicitly
        database = client.get_default_database()
        if database is None:  # <- explicit None check (no bool test)
            database = client["ideal_crop_suggester"]

        db.database = database
        db.users = database["users"]
        db.histories = database["histories"]
        db.subscriptions = database["subscriptions"]
        db.orders = database["orders"]
        db.usage = database["usage_counters"]

        # Ping to ensure connectivity (raises if Atlas not reachable/allowed)
        await client.admin.command("ping")

        # Ensure indexes AFTER collections are set
        await ensure_indexes()

    @app.on_event("shutdown")
    async def _shutdown():
        if db.client is not None:
            db.client.close()
            db.client = None
            db.database = None
            db.users = None
