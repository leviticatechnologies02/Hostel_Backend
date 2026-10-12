from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response
from sqlalchemy import select

from app.dependencies import CurrentUser, DBSession, require_roles
from app.schemas.booking import (
    BookingApplicantPatchRequest,
    BookingCancellationRequest,
    BookingInitiateRequest,
    BookingInitiateResponse,
    BookingResponse,
    BookingStatusHistoryResponse,
    CheckoutRequestCreate,
    CheckoutRequestResponse,
    WaitlistEntryResponse,
    WaitlistJoinRequest,
)
from app.schemas.payment import BookingPaymentCreateRequest, BookingPaymentOrderResponse
from app.services.booking_service import BookingService
from app.services.payment_write_service import PaymentWriteService
from app.tasks.booking_tasks import expire_draft_booking_task
from app.tasks.waitlist_tasks import notify_waitlist_joined_task
from app.models.booking import BookingStatusHistory

router = APIRouter()
VisitorUser = Annotated[CurrentUser, Depends(require_roles("visitor", "student", "hostel_admin", "supervisor", "super_admin"))]


@router.post("/initiate", response_model=BookingInitiateResponse, status_code=201)
async def initiate_booking(payload: BookingInitiateRequest, db: DBSession, current_user: VisitorUser):
    booking = await BookingService(db).initiate_booking(visitor_id=current_user.id, payload=payload)

    # Auto-expire draft after 30 minutes — fire-and-forget, don't fail if Redis is down.
    try:
        expire_draft_booking_task.apply_async(args=[str(booking.id)], countdown=30 * 60)
    except Exception:
        pass

    return BookingInitiateResponse(
        booking_id=str(booking.id),
        booking_number=booking.booking_number,
        status=booking.status.value,
        pricing={
            "base_rent_amount": float(booking.base_rent_amount),
            "security_deposit": float(booking.security_deposit),
            "booking_advance": float(booking.booking_advance),
            "grand_total": float(booking.grand_total),
            "payment_due_now": float(booking.booking_advance),
            "requires_full_payment": float(booking.security_deposit) == 0,
        },
    )


@router.patch("/{booking_id}", response_model=BookingResponse)
async def patch_booking_applicant(
    booking_id: str, payload: BookingApplicantPatchRequest, db: DBSession, current_user: VisitorUser
):
    return await BookingService(db).update_applicant_info(
        booking_id=booking_id,
        visitor_id=current_user.id,
        payload=payload,
    )


@router.post("/{booking_id}/payment", response_model=BookingPaymentOrderResponse, status_code=201)
async def create_payment(
    booking_id: str,
    payload: BookingPaymentCreateRequest,
    db: DBSession,
    current_user: VisitorUser,
):
    return await PaymentWriteService(db).create_booking_payment(
        booking_id=booking_id,
        actor_id=current_user.id,
        payload=payload,
    )


@router.post("/{booking_id}/payment/verify")
async def verify_payment(
    booking_id: str,
    db: DBSession,
    current_user: VisitorUser,
):
    """
    Called by the frontend after Razorpay payment success handler fires.
    Marks the payment as captured and moves booking to pending_approval.
    This is a fallback for when webhooks are not configured (e.g. local dev).
    """
    return await PaymentWriteService(db).verify_booking_payment(
        booking_id=booking_id,
        actor_id=current_user.id,
    )


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: str, db: DBSession, current_user: VisitorUser):
    booking = await BookingService(db).repository.get_by_id(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if str(booking.visitor_id) != str(current_user.id) and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Not your booking.")
    return booking


@router.get("/{booking_id}/history", response_model=list[BookingStatusHistoryResponse])
async def get_booking_history(booking_id: str, db: DBSession, current_user: VisitorUser):
    booking = await BookingService(db).repository.get_by_id(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if str(booking.visitor_id) != str(current_user.id) and current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Not your booking.")
    result = await db.execute(
        select(BookingStatusHistory)
        .where(BookingStatusHistory.booking_id == booking_id)
        .order_by(BookingStatusHistory.created_at.asc())
    )
    return [
        {
            "id": str(item.id),
            "booking_id": str(item.booking_id),
            "old_status": item.old_status.value if item.old_status else None,
            "new_status": item.new_status.value,
            "changed_by": str(item.changed_by) if item.changed_by else None,
            "note": item.note,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in result.scalars().all()
    ]


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    payload: BookingCancellationRequest,
    db: DBSession,
    current_user: VisitorUser,
):
    return await BookingService(db).cancel_booking(
        booking_id=booking_id,
        cancelled_by=current_user.id,
        reason=payload.reason,
    )


@router.post(
    "/{booking_id}/checkout-request",
    response_model=CheckoutRequestResponse,
    status_code=201,
)
async def request_checkout(
    booking_id: str,
    payload: CheckoutRequestCreate,
    db: DBSession,
    current_user: VisitorUser,
):
    """Request checkout. An admin must approve it before the bed is released."""
    return await BookingService(db).request_checkout(
        booking_id=booking_id,
        requested_by=current_user.id,
        reason=payload.reason,
    )


@router.get(
    "/{booking_id}/checkout-request",
    response_model=CheckoutRequestResponse,
)
async def get_checkout_request(
    booking_id: str,
    db: DBSession,
    current_user: VisitorUser,
):
    """Get the current user's checkout request and its admin decision."""
    return await BookingService(db).get_checkout_request(
        booking_id=booking_id, requested_by=current_user.id
    )


@router.patch("/{booking_id}/modify", response_model=BookingResponse)
async def modify_booking(
    booking_id: str,
    db: DBSession,
    current_user: VisitorUser,
):
    """
    **Request booking modification** — change check-in date or duration.
    Only allowed for APPROVED or PENDING_APPROVAL bookings.
    Hostel admin must re-approve after modification.
    """
    from pydantic import BaseModel as _BM
    from datetime import date as _date

    class ModifyRequest(_BM):
        check_in_date: _date | None = None
        check_out_date: _date | None = None
        note: str | None = None

    booking = await BookingService(db).repository.get_by_id(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if str(booking.visitor_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your booking.")
    from app.models.booking import BookingStatus
    if booking.status not in (BookingStatus.APPROVED, BookingStatus.PENDING_APPROVAL):
        raise HTTPException(status_code=400, detail=f"Cannot modify booking in '{booking.status.value}' status.")
    # Mark as pending approval again so admin re-reviews
    booking.status = BookingStatus.PENDING_APPROVAL
    await db.commit()
    await db.refresh(booking)
    return booking


@router.post("/waitlist/join", response_model=WaitlistEntryResponse, status_code=201)
async def join_waitlist(payload: WaitlistJoinRequest, db: DBSession, current_user: VisitorUser):
    """Join waitlist for a room when no beds are available."""
    try:
        # Validate room exists
        from app.models.room import Room
        room_result = await db.execute(select(Room).where(Room.id == payload.room_id))
        room = room_result.scalar_one_or_none()
        if not room:
            raise HTTPException(
                status_code=404, 
                detail=f"Room with id '{payload.room_id}' not found."
            )
        
        # Validate dates
        if payload.check_out_date <= payload.check_in_date:
            raise HTTPException(
                status_code=400,
                detail="check_out_date must be after check_in_date"
            )
        
        entry, position = await BookingService(db).join_waitlist(
            visitor_id=current_user.id, 
            payload=payload
        )
        
        return {
            "id": str(entry.id),
            "visitor_id": str(entry.visitor_id),
            "hostel_id": str(entry.hostel_id),
            "room_id": str(entry.room_id),
            "bed_id": str(entry.bed_id) if entry.bed_id else None,
            "booking_mode": entry.booking_mode.value if hasattr(entry.booking_mode, "value") else str(entry.booking_mode),
            "check_in_date": entry.check_in_date,
            "check_out_date": entry.check_out_date,
            "status": entry.status.value if hasattr(entry.status, "value") else str(entry.status),
            "position": position,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Waitlist join error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to join waitlist: {str(e)}")

@router.get("/waitlist/my", response_model=list[WaitlistEntryResponse])
async def my_waitlist(db: DBSession, current_user: VisitorUser):
    return await BookingService(db).list_my_waitlist(visitor_id=current_user.id)


@router.delete("/waitlist/{entry_id}", status_code=204)
async def leave_waitlist(entry_id: str, db: DBSession, current_user: VisitorUser):
    await BookingService(db).leave_waitlist(visitor_id=current_user.id, entry_id=entry_id)
    return Response(status_code=204)

