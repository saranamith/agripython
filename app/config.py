# app/config.py
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    # 🔑 Mongo & Auth
    mongodb_uri: str = os.getenv("MONGODB_URI", "")   # <-- make sure .env sets this
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret")
    jwt_expire_min: int = int(os.getenv("JWT_EXPIRE_MIN", "43200"))  # 30 days
    google_audience: str | None = os.getenv("GOOGLE_AUDIENCE")
    dev_passwordless: bool = os.getenv("DEV_PASSWORDLESS", "true").lower() == "true"

    # 🤖 LLM
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Razorpay Links
    razorpay_key_id: str = os.getenv("RAZORPAY_KEY_ID", "")
    razorpay_key_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    razorpay_webhook_secret: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    frontend_base_url: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

settings = Settings()
