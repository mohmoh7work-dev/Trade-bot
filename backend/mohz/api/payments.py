"""Payment history (read-only for now).

To plug in a provider later: create Payment rows from its webhook (provider + provider_ref
identify the charge and are unique together), set invoice_url to the provider's hosted
invoice, and change user.plan_id when a subscription starts or ends.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from ..auth import current_user
from ..db import get_db
from ..models import Payment, Plan
from .common import iso

router = APIRouter(prefix="/api", tags=["payments"])


@router.get("/payments")
def payments(user=Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())).all()
    return {"payments": [{"id": p.id, "date": iso(p.created_at), "amount_cents": p.amount_cents,
                          "currency": p.currency, "plan": p.plan.name if p.plan else None, "status": p.status,
                          "invoice_url": p.invoice_url} for p in rows]}


@router.get("/plans")
def plans(user=Depends(current_user), db=Depends(get_db)):
    return {"plans": [{"code": p.code, "name": p.name, "price_cents": p.price_cents, "currency": p.currency,
                       "interval": p.interval} for p in db.scalars(select(Plan).order_by(Plan.price_cents))]}
