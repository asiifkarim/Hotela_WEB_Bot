from __future__ import annotations

import logging
import re
import smtplib
from email.message import EmailMessage
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.db import SessionLocal
from app.models import Lead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class LeadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=320)
    business_type: str | None = Field(default=None, max_length=200)
    rooms: int | None = Field(default=None, ge=0, le=100000)
    plan_interest: str | None = Field(default=None, max_length=200)
    consent: bool

    @model_validator(mode="after")
    def contact_and_consent(self) -> "LeadRequest":
        if not self.consent:
            raise ValueError("Consent is required")
        if not self.phone and not self.email:
            raise ValueError("Phone or email is required")
        if self.email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", self.email):
            raise ValueError("Invalid email")
        return self


def masked(value: str | None) -> str:
    if not value:
        return ""
    return value[:2] + "***" + value[-2:]


@router.post("/leads")
def create_lead(payload: LeadRequest) -> dict[str, Any]:
    with SessionLocal() as db:
        lead = Lead(**payload.model_dump())
        db.add(lead)
        db.commit()
        db.refresh(lead)
    logger.info("Lead stored: name=%s email=%s phone=%s", payload.name, masked(payload.email), masked(payload.phone))
    if settings.smtp_host and settings.smtp_from:
        message = EmailMessage()
        message["Subject"] = "New Hotela chatbot lead"
        message["From"] = settings.smtp_from
        message["To"] = settings.handoff_email
        message.set_content(f"Name: {payload.name}\nEmail: {payload.email or ''}\nPhone: {payload.phone or ''}\nBusiness: {payload.business_type or ''}\nRooms: {payload.rooms or ''}\nPlan: {payload.plan_interest or ''}")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except Exception:
            logger.exception("Lead email notification failed")
    else:
        logger.info("SMTP is not configured; lead notification logged only")
    return {"ok": True, "lead_id": lead.id}


@router.post("/handoff")
def handoff(payload: dict[str, str | None]) -> dict[str, Any]:
    return {"email": settings.handoff_email, "whatsapp": settings.handoff_whatsapp or None, "summary": payload.get("summary")}
