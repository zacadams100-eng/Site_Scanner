"""
The enquiry route.

Separate from `routes_catalog` because it has nothing to do with assessing a
site: it is the one place the product accepts data from a user rather than
serving it. Mounted by both backends so the form works on any deployment.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

import enquiry as enquiry_mod

router = APIRouter()


class EnquiryRequest(BaseModel):
    """What the form sends.

    Lengths are capped at the point of entry. An unbounded free-text field on
    a public endpoint is how a form becomes a way to post megabytes into
    somebody's inbox.
    """

    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    organisation: str = Field("", max_length=160)
    site: str = Field("", max_length=400)
    detail: str = Field(..., min_length=1, max_length=4000)
    scanners: list[str] = Field(default_factory=list, max_length=8)


@router.get("/api/enquiry/status")
def enquiry_status() -> dict:
    """Whether this deployment can actually receive an enquiry.

    The form asks before it renders, so someone is told the form is not
    connected *before* they type five hundred words into it rather than after.
    Returns only whether a receiver exists — never which one, and never any
    part of its configuration.
    """
    return {"configured": enquiry_mod.configured_receiver() is not None}


@router.post("/api/enquiry")
def submit_enquiry(req: EnquiryRequest) -> dict:
    """Deliver an enquiry, or say plainly that it could not be delivered.

    **503 rather than 200 when there is no receiver.** A form that returns
    success when nothing received the submission is the same failure as a
    scanner reporting "clear" for a check it could not run, and this codebase
    does not do that in either place.
    """
    payload = enquiry_mod.Enquiry(
        name=req.name.strip(),
        email=str(req.email).strip(),
        organisation=req.organisation.strip(),
        site=req.site.strip(),
        detail=req.detail.strip(),
        scanners=tuple(s.strip() for s in req.scanners if s.strip()),
    )
    try:
        receiver = enquiry_mod.deliver(payload)
    except enquiry_mod.NotConfigured:
        raise HTTPException(
            status_code=503,
            detail="This form is not connected to a mailbox yet, so your "
                   "message was not sent and has not been stored.",
        )
    except Exception:
        # The reason is in the server log; the sender gets a fact they can act
        # on rather than a stack trace they cannot.
        raise HTTPException(
            status_code=502,
            detail="The enquiry could not be delivered. Nothing was stored — "
                   "please try again shortly.",
        )
    return {"delivered": True, "via": receiver}
