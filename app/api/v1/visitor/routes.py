from typing import Annotated
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, field_validator, field_validator
import re
from sqlalchemy import select, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timezone, date
import uuid
from app.dependencies import CurrentUser, DBSession, require_roles
from app.models.booking import Booking, BookingStatus
from app.models.hostel import Hostel
from app.models.operations import Review, Notice, NoticeRead
from app.models.user import User
from app.schemas.booking import BookingListResponse, BookingResponse, BookingCancellationRequest, WaitlistJoinRequest
from app.schemas.base import APIModel, TimestampedResponse
from app.schemas.notice import NoticeResponse
from app.schemas.mess_menu import MessMenuResponse
from app.schemas.upload import PresignedUploadRequest
from app.services.notice_service import NoticeService
from app.services.mess_menu_service import MessMenuService
from fastapi import APIRouter, Depends, HTTPException, status, Request
import re
from datetime import UTC, datetime
from app.core.security import verify_password, hash_password
from app.repositories.user_repository import UserRepository


def normalize_phone(phone: str) -> str:
    """Normalize phone number to standard format"""
    import re
    if not phone:
        return phone
    # Remove all non-digits
    digits = re.sub(r'[^0-9]', '', phone)
    if len(digits) < 10:
        raise ValueError("Phone number must have at least 10 digits")
    if len(digits) > 15:
        raise ValueError("Phone number must have at most 15 digits")
    # Return last 10 digits for Indian numbers
    return digits[-10:] if len(digits) > 10 else digits

router = APIRouter()
VisitorUser = Annotated[CurrentUser, Depends(require_roles("visitor", "student", "hostel_admin", "supervisor", "super_admin"))]
UTC = timezone.utc


# ── Schemas ──────────────────────────────────────────────────────────────────

class VisitorProfileResponse(APIModel):
    id: str
    email: str
    phone: str
    full_name: str
    role: str
    profile_picture_url: str | None = None
    is_email_verified: bool
    is_phone_verified: bool
    
class VisitorChangePasswordRequest(BaseModel):
    """Request to change visitor password"""
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)



class VisitorProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, min_length=10, max_length=15)  


class ReviewCreateRequest(BaseModel):
    hostel_id: str
    booking_id: str | None = None
    overall_rating: float = Field(ge=1, le=5)
    cleanliness_rating: float = Field(ge=1, le=5)
    food_rating: float = Field(ge=1, le=5)
    security_rating: float = Field(ge=1, le=5)
    value_rating: float = Field(ge=1, le=5)
    title: str = Field(min_length=3, max_length=255)
    content: str = Field(min_length=10)


class ReviewResponse(TimestampedResponse):
    id: str
    hostel_id: str
    visitor_id: str
    overall_rating: float
    cleanliness_rating: float
    food_rating: float
    security_rating: float
    value_rating: float
    title: str
    content: str
    is_verified: bool
    is_published: bool


class FavoriteResponse(APIModel):
    hostel_id: str
    hostel_name: str
    hostel_slug: str
    city: str
    hostel_type: str
    starting_price: float


# ==================== PROFILE ROUTES (static paths first) ====================

@router.get("/profile", response_model=VisitorProfileResponse)
async def get_profile(current_user: VisitorUser, db: DBSession):
    """**Get visitor profile.**"""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user

@router.patch("/profile", response_model=VisitorProfileResponse)
async def update_profile(payload: VisitorProfileUpdateRequest, current_user: VisitorUser, db: DBSession):
    """**Update visitor profile** — name, phone, profile picture."""
    import re
    
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Update full name (always safe)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    
    # Update profile picture (always safe)

    
    # Handle phone update separately (most likely the source of 500)
    if payload.phone is not None:
        # Clean the phone number
        digits = re.sub(r'[^0-9]', '', payload.phone)
        
        if len(digits) < 10:
            raise HTTPException(status_code=400, detail="Phone number must have at least 10 digits")
        
        # Standardize to last 10 digits
        standardized = digits[-10:] if len(digits) > 10 else digits
        
        # Only check for duplicates if the phone actually changed
        if standardized != user.phone:
            existing = await db.execute(
                select(User).where(User.phone == standardized, User.id != current_user.id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=409, 
                    detail=f"Phone number {standardized} is already registered"
                )
            user.phone = standardized
    
    await db.commit()
    await db.refresh(user)
    
    # Return the updated user
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "profile_picture_url": user.profile_picture_url,
        "is_email_verified": user.is_email_verified,
        "is_phone_verified": user.is_phone_verified,
    }
    
# ==================== NOTICE ROUTES (static paths BEFORE dynamic {notice_id}) ====================

@router.get("/notices/paginated")
async def visitor_notices_paginated(
    current_user: VisitorUser,
    db: DBSession,
    page: int = 1,
    per_page: int = 20,
):
    """
    **Get paginated notices visible to visitors.**
    """
    now = datetime.now(UTC)
    
    query = select(Notice).where(
        Notice.hostel_id.is_(None),  # Only platform-wide notices
        Notice.is_published == True,
        or_(
            Notice.publish_at.is_(None),
            Notice.publish_at <= now
        ),
        or_(
            Notice.expires_at.is_(None),
            Notice.expires_at > now
        )
    )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)
    
    # Get paginated results
    query = query.order_by(desc(Notice.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    notices = list(result.scalars().all())
    
    # Check read status for visitor
    items = []
    for notice in notices:
        read_result = await db.execute(
            select(NoticeRead).where(
                NoticeRead.notice_id == str(notice.id),
                NoticeRead.user_id == current_user.id
            )
        )
        is_read = read_result.scalar_one_or_none() is not None
        
        items.append({
            "id": str(notice.id),
            "hostel_id": None,
            "title": notice.title,
            "content": notice.content,
            "notice_type": notice.notice_type,
            "priority": notice.priority,
            "is_published": notice.is_published,
            "created_at": notice.created_at,
            "is_read": is_read,
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }



@router.get("/notices/read-status")
async def get_visitor_read_notice_ids(
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Get list of notice IDs that the visitor has read.**
    """
    result = await db.execute(
        select(NoticeRead.notice_id).where(NoticeRead.user_id == current_user.id)
    )
    return [str(notice_id) for notice_id in result.scalars().all()]


# IMPORTANT: Dynamic {notice_id} routes come AFTER static /notices/* routes
@router.get("/notices/{notice_id}")
async def get_visitor_notice(
    notice_id: str,
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Get a single notice by ID (only platform-wide notices).**
    """
    result = await db.execute(
        select(Notice).where(
            Notice.id == notice_id,
            Notice.hostel_id.is_(None),
            Notice.is_published.is_(True),
        )
    )
    notice = result.scalar_one_or_none()
    
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found or not published.")
    
    # Check if already read
    read_result = await db.execute(
        select(NoticeRead).where(
            NoticeRead.notice_id == notice_id,
            NoticeRead.user_id == current_user.id,
        )
    )
    is_read = read_result.scalar_one_or_none() is not None
    
    return {
        "id": str(notice.id),
        "hostel_id": None,
        "title": notice.title,
        "content": notice.content,
        "notice_type": notice.notice_type,
        "priority": notice.priority,
        "is_published": notice.is_published,
        "created_at": notice.created_at,
        "is_read": is_read,
    }


@router.post("/notices/{notice_id}/read")
async def mark_visitor_notice_read(
    notice_id: str,
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Mark a platform-wide notice as read by the visitor.**
    """
    # Check if notice exists and is published
    result = await db.execute(
        select(Notice).where(
            Notice.id == notice_id,
            Notice.hostel_id.is_(None),
            Notice.is_published.is_(True),
        )
    )
    notice = result.scalar_one_or_none()
    
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found or not published.")
    
    # Check if already marked as read
    read_result = await db.execute(
        select(NoticeRead).where(
            NoticeRead.notice_id == notice_id,
            NoticeRead.user_id == current_user.id,
        )
    )
    existing = read_result.scalar_one_or_none()
    
    if existing is None:
        notice_read = NoticeRead(
            notice_id=notice_id,
            user_id=current_user.id,
        )
        db.add(notice_read)
        await db.commit()
    
    return {"notice_id": notice_id, "is_read": True}


# ==================== BOOKING ROUTES ====================

@router.get("/bookings", response_model=list[BookingListResponse])
async def list_bookings(current_user: VisitorUser, db: DBSession):
    """**List all bookings for the authenticated visitor.**"""
    from app.services.visitor_service import VisitorService
    return await VisitorService(db).list_bookings(current_user.id)


@router.get("/bookings/{booking_id}/status-history")
async def get_booking_status_history(
    booking_id: str,
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Get status history for a specific booking.**
    """
    from app.models.booking import Booking, BookingStatusHistory
    
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    
    if str(booking.visitor_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your booking.")
    
    history_result = await db.execute(
        select(BookingStatusHistory)
        .where(BookingStatusHistory.booking_id == booking_id)
        .order_by(BookingStatusHistory.created_at.asc())
    )
    
    return [
        {
            "id": str(item.id),
            "old_status": item.old_status.value if item.old_status else None,
            "new_status": item.new_status.value,
            "changed_by": str(item.changed_by) if item.changed_by else None,
            "note": item.note,
            "created_at": item.created_at,
        }
        for item in history_result.scalars().all()
    ]


@router.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(booking_id: str, payload: BookingCancellationRequest, current_user: VisitorUser, db: DBSession):
    """**Cancel a booking.** Only allowed for payment_pending or pending_approval status."""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if str(booking.visitor_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your booking.")
    if booking.status not in (BookingStatus.PAYMENT_PENDING, BookingStatus.PENDING_APPROVAL):
        raise HTTPException(status_code=400, detail=f"Cannot cancel booking in '{booking.status.value}' status.")
    booking.status = BookingStatus.CANCELLED
    booking.cancellation_reason = payload.reason
    await db.commit()
    await db.refresh(booking)
    return booking


# ==================== REVIEW ROUTES ====================

@router.post("/reviews", response_model=ReviewResponse, status_code=201)
async def submit_review(payload: ReviewCreateRequest, current_user: VisitorUser, db: DBSession):
    """**Submit a review for a hostel.** One review per visitor per hostel."""
    # Check for duplicate
    existing = await db.execute(
        select(Review).where(Review.visitor_id == current_user.id, Review.hostel_id == payload.hostel_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You have already reviewed this hostel.")
    if payload.booking_id:
        booking_result = await db.execute(select(Booking).where(Booking.id == payload.booking_id))
        booking = booking_result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found.")
        if str(booking.visitor_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Not your booking.")
        if str(booking.hostel_id) != payload.hostel_id:
            raise HTTPException(status_code=400, detail="Booking does not belong to this hostel.")
        if booking.status != BookingStatus.CHECKED_OUT:
            raise HTTPException(status_code=400, detail="Reviews are allowed only after checkout.")
    else:
        booking_result = await db.execute(
            select(Booking)
            .where(
                Booking.visitor_id == current_user.id,
                Booking.hostel_id == payload.hostel_id,
                Booking.status == BookingStatus.CHECKED_OUT,
            )
            .order_by(Booking.check_out_date.desc())
        )
        checked_out_booking = booking_result.scalars().first()
        if not checked_out_booking:
            raise HTTPException(status_code=400, detail="You can review this hostel only after checkout.")
    review = Review(
        visitor_id=current_user.id,
        hostel_id=payload.hostel_id,
        booking_id=payload.booking_id,
        overall_rating=payload.overall_rating,
        cleanliness_rating=payload.cleanliness_rating,
        food_rating=payload.food_rating,
        security_rating=payload.security_rating,
        value_rating=payload.value_rating,
        title=payload.title,
        content=payload.content,
        is_verified=False,
        is_published=True,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


@router.get("/reviews", response_model=list[ReviewResponse])
async def list_my_reviews(current_user: VisitorUser, db: DBSession):
    """**List all reviews submitted by the visitor.**"""
    result = await db.execute(
        select(Review).where(Review.visitor_id == current_user.id).order_by(Review.created_at.desc())
    )
    return list(result.scalars().all())


# ==================== FAVORITE ROUTES (static paths BEFORE dynamic {hostel_id}) ====================

@router.get("/favorites", response_model=list[FavoriteResponse])
async def list_favorites(current_user: VisitorUser, db: DBSession):
    """**List saved/favorite hostels.**"""
    from app.models.hostel import VisitorFavorite
    result = await db.execute(
        select(Hostel)
        .join(VisitorFavorite, VisitorFavorite.hostel_id == Hostel.id)
        .where(VisitorFavorite.visitor_id == current_user.id)
        .order_by(VisitorFavorite.created_at.desc())
    )
    hostels = result.scalars().all()
    return [
        FavoriteResponse(
            hostel_id=str(h.id),
            hostel_name=h.name,
            hostel_slug=h.slug,
            city=h.city,
            hostel_type=h.hostel_type.value if hasattr(h.hostel_type, "value") else str(h.hostel_type),
            starting_price=0.0,
        )
        for h in hostels
    ]


@router.post("/favorites/compare")
async def compare_favorites(
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Compare favorite hostels side by side.**
    """
    from app.models.hostel import VisitorFavorite, Hostel, HostelAmenity
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Hostel)
        .join(VisitorFavorite, VisitorFavorite.hostel_id == Hostel.id)
        .where(VisitorFavorite.visitor_id == current_user.id)
        .options(selectinload(Hostel.amenities))
    )
    favorites = list(result.scalars().all())
    
    comparison = []
    for hostel in favorites:
        comparison.append({
            "id": str(hostel.id),
            "name": hostel.name,
            "slug": hostel.slug,
            "city": hostel.city,
            "hostel_type": hostel.hostel_type.value if hasattr(hostel.hostel_type, "value") else str(hostel.hostel_type),
            "description": hostel.description[:200] if hostel.description else "",
            "amenities": [a.name for a in hostel.amenities],
            "rating": 0.0,
            "starting_price": 0.0,
        })
    
    return comparison


# IMPORTANT: Dynamic {hostel_id} routes come AFTER static /favorites/* routes
@router.post("/favorites/{hostel_id}", status_code=201)
async def add_favorite(hostel_id: str, current_user: VisitorUser, db: DBSession):
    """**Save a hostel to favorites.**"""
    from app.models.hostel import VisitorFavorite
    
    # Validate hostel_id is a valid UUID
    import uuid
    try:
        uuid.UUID(hostel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hostel ID format.")
    
    existing = await db.execute(
        select(VisitorFavorite).where(
            VisitorFavorite.visitor_id == current_user.id,
            VisitorFavorite.hostel_id == hostel_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Already in favorites."}
    db.add(VisitorFavorite(visitor_id=current_user.id, hostel_id=hostel_id))
    await db.commit()
    return {"message": "Added to favorites.", "hostel_id": hostel_id}


@router.delete("/favorites/{hostel_id}", status_code=200)
async def remove_favorite(hostel_id: str, current_user: VisitorUser, db: DBSession):
    """**Remove a hostel from favorites.**"""
    from app.models.hostel import VisitorFavorite
    
    # Validate hostel_id is a valid UUID
    import uuid
    try:
        uuid.UUID(hostel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hostel ID format.")
    
    result = await db.execute(
        select(VisitorFavorite).where(
            VisitorFavorite.visitor_id == current_user.id,
            VisitorFavorite.hostel_id == hostel_id,
        )
    )
    fav = result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()
    return {"message": "Removed from favorites.", "hostel_id": hostel_id}


# ==================== MESS MENU ROUTES ====================

@router.get("/hostels/{hostel_id}/mess-menu", response_model=list[MessMenuResponse])
async def get_hostel_mess_menu(
    hostel_id: str,
    db: DBSession,
):
    """
    **Get mess menu for a specific hostel (public view).**
    
    Visitors can view mess menus of any public hostel.
    """
    # Validate hostel_id is a valid UUID
    import uuid
    try:
        uuid.UUID(hostel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hostel ID format.")
    
    # Check if hostel exists and is public
    result = await db.execute(
        select(Hostel).where(
            Hostel.id == hostel_id,
            Hostel.is_public == True,
            Hostel.status == "active"
        )
    )
    hostel = result.scalar_one_or_none()
    
    if not hostel:
        raise HTTPException(status_code=404, detail="Hostel not found or not public.")
    
    menus = await MessMenuService(db).list_admin_menus(hostel_id=hostel_id)
    return menus


# ==================== WAITLIST ROUTES ====================

# Replace the waitlist section in visitor/routes.py

# ==================== WAITLIST (Visitors can join waitlists) ====================

@router.post("/waitlist/join")
async def visitor_join_waitlist(
    payload: WaitlistJoinRequest,
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Join waitlist for a room when no beds are available.**
    """
    from app.services.booking_service import BookingService
    from app.models.room import Room
    
    # Validate room exists
    try:
        uuid.UUID(payload.room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room ID format.")
    
    # Validate hostel exists
    try:
        uuid.UUID(payload.hostel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hostel ID format.")
    
    room_result = await db.execute(select(Room).where(Room.id == payload.room_id))
    room = room_result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail=f"Room with id '{payload.room_id}' not found.")
    
    # Validate dates
    if payload.check_out_date <= payload.check_in_date:
        raise HTTPException(
            status_code=400,
            detail="check_out_date must be after check_in_date"
        )
    
    # Check if check_in_date is not too far in the past
    if payload.check_in_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Check-in date cannot be in the past"
        )
    
    try:
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
            "check_in_date": entry.check_in_date.isoformat(),
            "check_out_date": entry.check_out_date.isoformat(),
            "status": entry.status.value if hasattr(entry.status, "value") else str(entry.status),
            "position": position,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Waitlist join error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to join waitlist: {str(e)}")


@router.get("/waitlist")
async def visitor_waitlist(
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **List visitor's waitlist entries.**
    """
    from app.services.booking_service import BookingService
    return await BookingService(db).list_my_waitlist(visitor_id=current_user.id)


@router.delete("/waitlist/{entry_id}")
async def visitor_leave_waitlist(
    entry_id: str,
    current_user: VisitorUser,
    db: DBSession,
):
    """
    **Leave/cancel a waitlist entry.**
    """
    from app.services.booking_service import BookingService
    await BookingService(db).leave_waitlist(
        visitor_id=current_user.id,
        entry_id=entry_id
    )
    return Response(status_code=204)


# ==================== FILE UPLOAD ROUTES ====================

@router.post("/uploads/presigned-url")
async def visitor_presigned_upload_url(
    payload: PresignedUploadRequest,
    current_user: VisitorUser,
    request: Request,
):
    """
    **Generate S3 presigned upload URL for visitor documents (ID proof, etc.).**
    """
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
    content_type = payload.content_type.strip().lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: jpg, png, webp, pdf.",
        )
    
    # Fix: Check file size and return 400, not 422
    if payload.file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,  # Changed from 422 to 400
            detail="File size exceeds 10MB limit.",
        )
    
    from app.integrations.cloudinary_client import get_cloudinary_client
    base_url = str(request.base_url).rstrip('/')
    return await get_cloudinary_client().get_presigned_upload_url(
        file_name=payload.file_name,
        content_type=content_type,
        api_base_url=base_url
    )
    
@router.post("/change-password")
async def change_visitor_password(
    payload: VisitorChangePasswordRequest,
    current_user: VisitorUser,
    db: DBSession
):
    """
    **Change visitor password.**
    
    Requirements:
    - Current password must be correct
    - New password: min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char
    - New password and confirm password must match
    
    After successful change, all other sessions are revoked for security.
    """
    from app.models.user import User
    from sqlalchemy import select
    
    # Validate passwords match
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match."
        )
    
    # Get the user record
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Verify current password
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Current password is incorrect."
        )
    
    # Validate new password strength
    errors = []
    if len(payload.new_password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r'[A-Z]', payload.new_password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', payload.new_password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', payload.new_password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', payload.new_password):
        errors.append("Password must contain at least one special character")
    
    if errors:
        raise HTTPException(
            status_code=400,
            detail="; ".join(errors)
        )
    
    # Hash and update password
    user.password_hash = hash_password(payload.new_password)
    
    # Revoke all other sessions for security (keep current)
    repo = UserRepository(db)
    await repo.revoke_all_refresh_tokens(
        user_id=current_user.id,
        revoked_at=datetime.now(UTC)
    )
    
    await db.commit()
    
    return {
        "message": "Password changed successfully.",
        "user_id": str(user.id)
    }
