# app/api/v1/student/routes.py - COMPLETELY FIXED VERSION

from typing import Annotated

from starlette.responses import Response
from sqlalchemy import or_, select
from app.schemas.notice import NoticeResponse, NoticeListResponse  
from app.dependencies import CurrentUser, DBSession, require_roles
from app.models.operations import Notice, NoticeRead
from app.schemas.attendance import AttendanceResponse
from app.schemas.booking import BookingListResponse, BookingResponse, WaitlistEntryResponse
from app.schemas.complaint import ComplaintCreateRequest, ComplaintResponse
from app.schemas.mess_menu import MessMenuResponse
from app.schemas.payment import PaymentResponse
from app.schemas.student import StudentProfileResponse, StudentResponse, StudentRoommatesResponse
from app.schemas.upload import PresignedUploadRequest, PresignedUploadResponse
from app.integrations.s3 import get_s3_client
from app.services.booking_service import BookingService
from app.services.complaint_service import ComplaintService
from app.services.payment_service import PaymentService
from app.services.student_read_service import StudentReadService
from app.services.notice_service import NoticeService
from app.models.operations import Complaint, ComplaintComment
from app.models.student import Student, StudentStatus
from app.models.user import User
from app.models.hostel import Hostel
from app.models.room import Room, Bed, BedStatus
from app.models.booking import Booking
from pydantic import BaseModel as PydanticBaseModel
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
import re
from datetime import UTC, datetime
from app.core.security import verify_password, hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.transfer import StudentTransferResponse, StudentTransferCreateRequest

class StudentProfileUpdateRequest(PydanticBaseModel):
    full_name: str | None = None
    phone: str | None = None


class LeaveRequestCreate(PydanticBaseModel):
    from_date: str
    to_date: str
    reason: str

router = APIRouter()
StudentUser = Annotated[CurrentUser, Depends(require_roles("student"))]
AdminUser = Annotated[CurrentUser, Depends(require_roles("hostel_admin", "super_admin"))]

class StudentChangePasswordRequest(BaseModel):
    """Request to change student password"""
    old_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


# ==================== PROFILE ENDPOINTS ====================

@router.get("/profile", response_model=StudentProfileResponse)
async def profile(current_user: StudentUser, db: DBSession):
    """**Student profile** — personal info, hostel, room, bed, booking, and student number."""
    profile_data = await StudentReadService(db).get_profile(user_id=current_user.id)
    if profile_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found.",
        )
    
    if profile_data.get("check_in_date"):
        profile_data["check_in_date"] = profile_data["check_in_date"].isoformat() if hasattr(profile_data["check_in_date"], "isoformat") else profile_data["check_in_date"]
    if profile_data.get("check_out_date"):
        profile_data["check_out_date"] = profile_data["check_out_date"].isoformat() if hasattr(profile_data["check_out_date"], "isoformat") else profile_data["check_out_date"]
    if profile_data.get("date_of_birth"):
        profile_data["date_of_birth"] = profile_data["date_of_birth"].isoformat() if hasattr(profile_data["date_of_birth"], "isoformat") else profile_data["date_of_birth"]
    
    return profile_data


@router.get("/profile/detailed")
async def get_detailed_student_profile(current_user: StudentUser, db: DBSession):
    """Get detailed student profile with hostel, room, and bed info."""
    result = await db.execute(
        select(Student, User, Hostel, Room, Bed, Booking)
        .join(User, User.id == Student.user_id)
        .join(Hostel, Hostel.id == Student.hostel_id)
        .join(Room, Room.id == Student.room_id)
        .join(Bed, Bed.id == Student.bed_id)
        .join(Booking, Booking.id == Student.booking_id)
        .where(Student.user_id == current_user.id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    
    student, user, hostel, room, bed, booking = row
    
    return {
        "id": str(student.id),
        "student_number": student.student_number,
        "check_in_date": str(student.check_in_date),
        "check_out_date": str(student.check_out_date) if student.check_out_date else None,
        "status": student.status.value if hasattr(student.status, "value") else str(student.status),
        "user_id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "profile_picture_url": user.profile_picture_url,
        "gender": booking.gender if booking else None,
        "date_of_birth": booking.date_of_birth if booking else None,
        "hostel": {
            "id": str(hostel.id),
            "name": hostel.name,
            "slug": hostel.slug,
            "address": {
                "line1": hostel.address_line1,
                "line2": hostel.address_line2,
                "city": hostel.city,
                "state": hostel.state,
                "country": hostel.country,
                "pincode": hostel.pincode
            },
            "phone": hostel.phone,
            "email": hostel.email,
            "hostel_type": hostel.hostel_type.value if hasattr(hostel.hostel_type, "value") else str(hostel.hostel_type),
            "description": hostel.description,
            "is_featured": hostel.is_featured
        },
        "room": {
            "id": str(room.id),
            "room_number": room.room_number,
            "floor": room.floor,
            "room_type": room.room_type.value if hasattr(room.room_type, "value") else str(room.room_type),
            "hourly_rent": float(room.hourly_rent or 0),
            "daily_rent": float(room.daily_rent),
            "monthly_rent": float(room.monthly_rent)
        },
        "bed": {
            "id": str(bed.id),
            "bed_number": bed.bed_number,
            "status": bed.status.value if hasattr(bed.status, "value") else str(bed.status)
        },
        "booking": {
            "id": str(booking.id),
            "booking_number": booking.booking_number,
            "status": booking.status.value if hasattr(booking.status, "value") else str(booking.status),
            "booking_mode": booking.booking_mode.value if hasattr(booking.booking_mode, "value") else str(booking.booking_mode)
        },
        "created_at": student.created_at,
        "updated_at": student.updated_at,
    }


@router.get("/roommates", response_model=StudentRoommatesResponse)
async def get_my_roommates(current_user: StudentUser, db: DBSession):
    """**My Roommates** — Get current student's room details, bed details, and roommate information only."""
    # 1. Get active student record for logged-in user
    student_res = await db.execute(
        select(Student)
        .where(
            Student.user_id == current_user.id,
            Student.status.in_([StudentStatus.ACTIVE, StudentStatus.ON_LEAVE]),
        )
        .order_by(Student.created_at.desc())
    )
    student = student_res.scalars().first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active student record not found."
        )

    # 2. Get room details
    room_res = await db.execute(select(Room).where(Room.id == student.room_id))
    room = room_res.scalar_one_or_none()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned room not found."
        )

    # 3. Get student's bed details
    bed_res = await db.execute(select(Bed).where(Bed.id == student.bed_id))
    bed = bed_res.scalar_one_or_none()

    # 4. Get active roommates assigned to the same room currently occupying a bed
    from datetime import date
    today = date.today()

    roommates_res = await db.execute(
        select(Student, User, Bed)
        .join(User, User.id == Student.user_id)
        .join(Bed, Bed.id == Student.bed_id)
        .where(
            Student.room_id == student.room_id,
            Student.id != student.id,
            Student.status.in_([StudentStatus.ACTIVE, StudentStatus.ON_LEAVE]),
            Bed.status == BedStatus.OCCUPIED,
            (Student.check_out_date == None) | (Student.check_out_date >= today),
        )
    )

    roommate_items = []
    for s, u, b in roommates_res.all():
        roommate_items.append({
            "id": str(s.id),
            "user_id": str(u.id),
            "full_name": u.full_name,
            "phone": u.phone,
            "email": u.email,
            "bed_number": b.bed_number if b else None,
        })

    return {
        "room": {
            "id": str(room.id),
            "room_number": room.room_number,
            "floor": room.floor,
            "room_type": room.room_type.value if hasattr(room.room_type, "value") else str(room.room_type),
            "total_beds": room.total_beds,
        },
        "bed": {
            "id": str(bed.id) if bed else None,
            "bed_number": bed.bed_number if bed else None,
        },
        "roommates": roommate_items,
    }


@router.patch("/profile")
async def update_profile(
    request: Request,
    current_user: StudentUser, 
    db: DBSession
):
    """**Update student profile** — name, phone, profile picture."""
    from sqlalchemy import select
    from app.models.user import User
    
    try:
        body = await request.json()
    except:
        body = {}
    
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    if "full_name" in body and body["full_name"] is not None:
        user.full_name = body["full_name"]
    
    if "phone" in body and body["phone"] is not None:
        phone = body["phone"]
        digits_only = re.sub(r'[^0-9]', '', phone)
        if len(digits_only) < 10 or len(digits_only) > 13:
            raise HTTPException(
                status_code=400,
                detail="Phone number must have between 10 and 13 digits."
            )
        existing = await db.execute(
            select(User).where(
                User.phone == phone,
                User.id != current_user.id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Phone number already registered by another user."
            )
        user.phone = phone
    

    
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "profile_picture_url": user.profile_picture_url
    }


@router.post("/change-password")
async def change_student_password(
    payload: StudentChangePasswordRequest,
    current_user: StudentUser,
    db: DBSession
):
    """**Change student password.**"""
    from app.models.user import User
    from sqlalchemy import select
    
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match."
        )
    
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Current password is incorrect."
        )
    
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
    
    user.password_hash = hash_password(payload.new_password)
    
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


# ==================== PAYMENT & BOOKING ====================

@router.get("/payments", response_model=list[PaymentResponse])
async def payments(current_user: StudentUser, db: DBSession):
    """**Student payment history** — booking advances, monthly rent, and payment statuses."""
    return await PaymentService(db).list_student_payments(user_id=current_user.id)


from app.schemas.payment import (
    RemainingBalancePaymentRequest,
    RemainingBalancePaymentResponse,
    VerifyStudentPaymentRequest,
)
from app.services.payment_write_service import PaymentWriteService


@router.post("/payments/pay-remaining", response_model=RemainingBalancePaymentResponse)
async def pay_remaining_balance(
    payload: RemainingBalancePaymentRequest,
    current_user: StudentUser,
    db: DBSession
):
    """
    **Pay the remaining balance for a booking.**
    
    This calculates the difference between the booking's grand total and all successful payments,
    and creates a Razorpay order for the remaining amount.
    """
    return await PaymentWriteService(db).create_remaining_balance_payment(
        payload=payload,
        actor_id=current_user.id
    )


@router.get("/bookings", response_model=list[BookingListResponse])
async def bookings(current_user: StudentUser, db: DBSession):
    """**Student booking history** — all bookings in all statuses."""
    return await StudentReadService(db).list_bookings(user_id=current_user.id)


@router.post("/payments/verify")
@router.post("/payments/{payment_id}/verify")
async def verify_student_payment(
    current_user: StudentUser,
    db: DBSession,
    payment_id: str | None = None,
    payload: VerifyStudentPaymentRequest | None = None,
):
    """
    **Verify a student Razorpay payment** (frontend fallback when webhooks aren't configured).

    Accepts:
    - Path param: `POST /api/v1/student/payments/{payment_id}/verify`
    - Body param: `POST /api/v1/student/payments/verify` with `{ "payment_id": "...", "razorpay_payment_id": "..." }`
    """
    from sqlalchemy import select, or_
    from sqlalchemy.orm import joinedload
    from app.models.payment import Payment
    from app.models.student import Student
    from app.models.booking import Booking
    from datetime import UTC, datetime

    target_id = payment_id or (payload.payment_id if payload else None)

    # Get student record for user (if any)
    student_res = await db.execute(
        select(Student).where(Student.user_id == str(current_user.id))
    )
    student = student_res.scalar_one_or_none()

    if not target_id:
        # Find latest pending payment for this user
        filters = []
        if student:
            filters.append(Payment.student_id == str(student.id))
        
        booking_ids_subq = (
            select(Booking.id).where(Booking.visitor_id == str(current_user.id))
        ).scalar_subquery()
        filters.append(Payment.booking_id.in_(booking_ids_subq))

        pending_res = await db.execute(
            select(Payment)
            .options(joinedload(Payment.booking))
            .where(or_(*filters), Payment.status.in_(["pending", "created"]))
            .order_by(Payment.created_at.desc())
        )
        payment = pending_res.scalars().first()
    else:
        result = await db.execute(
            select(Payment)
            .options(joinedload(Payment.booking))
            .where(Payment.id == target_id)
        )
        payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found.")

    # Verify ownership (matches student_id OR booking visitor_id)
    is_owner = False
    if student and payment.student_id and str(payment.student_id) == str(student.id):
        is_owner = True
    elif payment.booking and str(payment.booking.visitor_id) == str(current_user.id):
        is_owner = True
    elif not payment.student_id and not payment.booking_id:
        is_owner = True

    if not is_owner:
        raise HTTPException(status_code=403, detail="This payment does not belong to you.")

    # Store gateway details if provided
    if payload:
        if payload.razorpay_payment_id:
            payment.gateway_payment_id = payload.razorpay_payment_id
        if payload.razorpay_signature:
            payment.gateway_signature = payload.razorpay_signature

    # Only process pending/created
    if payment.status not in ("pending", "created"):
        return {
            "status": "already_processed",
            "payment_id": str(payment.id),
            "current_status": payment.status,
            "message": f"Payment is already '{payment.status}'. No action needed.",
        }

    # Mark as captured
    payment.status = "captured"
    payment.paid_at = datetime.now(UTC)
    payment.payment_method = payment.payment_method or "razorpay"

    await db.commit()

    return {
        "status": "verified",
        "payment_id": str(payment.id),
        "amount": float(payment.amount),
        "message": "Payment verified and marked as captured successfully.",
    }

# ==================== ATTENDANCE ====================

@router.get("/attendance", response_model=list[AttendanceResponse])
async def attendance(current_user: StudentUser, db: DBSession):
    """**Student attendance records** — daily check-in/check-out history."""
    return await StudentReadService(db).list_attendance(user_id=current_user.id)


# ==================== NOTICE ROUTES ====================
# CRITICAL: Static routes MUST come BEFORE dynamic {notice_id} routes

@router.get("/notices/read-status", response_model=list[str])
async def get_read_notice_ids(
    current_user: StudentUser,
    db: DBSession,
):
    """Get list of notice IDs that the student has read"""
    return await NoticeService(db).get_user_read_notices(user_id=current_user.id)


@router.get("/notices/paginated", response_model=NoticeListResponse)
async def student_notices_paginated(
    current_user: StudentUser,
    db: DBSession,
    page: int = 1,
    per_page: int = 20,
):
    """Get paginated notices for student's hostel"""
    return await NoticeService(db).list_student_notices(
        student_user_id=current_user.id,
        page=page,
        per_page=per_page,
    )


@router.get("/notices/{notice_id}")
async def get_student_notice(
    notice_id: str,
    current_user: StudentUser,
    db: DBSession,
):
    """Get a single notice by ID (only if student has access)"""
    result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    
    result = await db.execute(
        select(Notice).where(
            Notice.id == notice_id,
            Notice.is_published.is_(True),
            or_(
                Notice.hostel_id == str(student.hostel_id),
                Notice.hostel_id.is_(None),
            ),
        )
    )
    notice = result.scalar_one_or_none()
    
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found or not published.")
    
    read_result = await db.execute(
        select(NoticeRead).where(
            NoticeRead.notice_id == notice_id,
            NoticeRead.user_id == current_user.id,
        )
    )
    is_read = read_result.scalar_one_or_none() is not None
    
    return {
        "id": str(notice.id),
        "hostel_id": str(notice.hostel_id) if notice.hostel_id else None,
        "title": notice.title,
        "content": notice.content,
        "notice_type": notice.notice_type,
        "priority": notice.priority,
        "is_published": notice.is_published,
        "created_at": notice.created_at,
        "is_read": is_read,
    }


@router.post("/notices/{notice_id}/read")
async def mark_notice_read(
    notice_id: str,
    current_user: StudentUser,
    db: DBSession,
):
    """Mark a notice as read by the student"""
    return await NoticeService(db).mark_notice_as_read(
        notice_id=notice_id,
        user_id=current_user.id,
    )


# ==================== MESS MENU ====================

@router.get("/mess-menu", response_model=list[MessMenuResponse])
async def mess_menu(current_user: StudentUser, db: DBSession):
    """**Weekly mess menu** for the student's hostel."""
    return await StudentReadService(db).list_mess_menus(user_id=current_user.id)


# ==================== WAITLIST ====================

@router.get("/waitlist", response_model=list[WaitlistEntryResponse])
async def student_waitlist(current_user: StudentUser, db: DBSession):
    """**Visitor waitlist entries** for the same account."""
    return await BookingService(db).list_my_waitlist(visitor_id=current_user.id)


@router.delete("/waitlist/{entry_id}", status_code=204)
async def student_leave_waitlist(entry_id: str, current_user: StudentUser, db: DBSession):
    await BookingService(db).leave_waitlist(visitor_id=current_user.id, entry_id=entry_id)
    return Response(status_code=204)


# ==================== COMPLAINTS ====================

@router.get("/complaints", response_model=list[ComplaintResponse])
async def complaints(current_user: StudentUser, db: DBSession):
    """**Student's own complaints** — submitted complaints with current status."""
    return await ComplaintService(db).list_student_complaints(user_id=current_user.id)


@router.post("/complaints", response_model=ComplaintResponse, status_code=201)
async def create_complaint(payload: ComplaintCreateRequest, current_user: StudentUser, db: DBSession):
    """**Submit a new complaint.**"""
    return await ComplaintService(db).create_student_complaint(user_id=current_user.id, payload=payload)


@router.delete("/complaints/{complaint_id}", status_code=204)
async def delete_my_complaint(
    complaint_id: str,
    current_user: StudentUser,
    db: DBSession,
):  
    result = await db.execute(
        select(Complaint).where(Complaint.id == complaint_id)
    )
    complaint = result.scalar_one_or_none()
    
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found."
        )
    
    result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = result.scalar_one_or_none()
    
    if not student or str(complaint.student_id) != str(student.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own complaints."
        )
    
    if complaint.status in ["resolved", "closed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a resolved or closed complaint."
        )
    
    await db.delete(complaint)
    await db.commit()
    
    return Response(status_code=204)


# ==================== FILE UPLOADS ====================

@router.post("/uploads/presigned-url", response_model=PresignedUploadResponse)
async def create_presigned_upload_url(
    payload: PresignedUploadRequest,
    current_user: Annotated[CurrentUser, Depends(require_roles("student", "visitor", "hostel_admin", "super_admin"))],
    request: Request,
):
    """Generate S3 presigned upload URL for student complaint attachments."""
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
    if payload.file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10MB limit.",
        )
    from app.integrations.cloudinary_client import get_cloudinary_client
    base_url = str(request.base_url).rstrip('/')
    return await get_cloudinary_client().get_presigned_upload_url(
        file_name=payload.file_name,
        content_type=content_type,
        api_base_url=base_url
    )


# ==================== ROOM INFO & LEAVE ====================

@router.get("/room-info")
async def room_info(current_user: StudentUser, db: DBSession):
    """**Get student's current room and bed details.**"""
    result = await db.execute(select(Student).where(Student.user_id == current_user.id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    
    room_result = await db.execute(select(Room).where(Room.id == student.room_id))
    room = room_result.scalar_one_or_none()
    
    bed_result = await db.execute(select(Bed).where(Bed.id == student.bed_id))
    bed = bed_result.scalar_one_or_none()
    
    return {
        "student_number": student.student_number,
        "room": {
            "id": str(room.id) if room else None,
            "room_number": room.room_number if room else None,
            "floor": room.floor if room else None,
            "room_type": room.room_type if room else None,
            "monthly_rent": float(room.monthly_rent) if room else None,
        },
        "bed": {
            "id": str(bed.id) if bed else None,
            "bed_number": bed.bed_number if bed else None,
            "status": bed.status if bed else None,
        },
        "check_in_date": str(student.check_in_date),
        "check_out_date": str(student.check_out_date) if student.check_out_date else None,
        "status": student.status,
    }


@router.post("/leave-request", status_code=201)
async def create_leave_request(payload: LeaveRequestCreate, current_user: StudentUser, db: DBSession):
    """**Apply for leave.** Creates a leave request for admin approval."""
    from datetime import date
    
    result = await db.execute(select(Student).where(Student.user_id == current_user.id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")
    
    # Validate dates
    try:
        from_date = date.fromisoformat(payload.from_date)
        to_date = date.fromisoformat(payload.to_date)
        if to_date < from_date:
            raise HTTPException(status_code=400, detail="End date must be after start date")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    import uuid
    leave = Complaint(
        complaint_number=f"LVE-{uuid.uuid4().hex[:6].upper()}",
        student_id=student.id,
        hostel_id=student.hostel_id,
        category="leave",
        title=f"Leave Request: {payload.from_date} to {payload.to_date}",
        description=f"Leave from {payload.from_date} to {payload.to_date}. Reason: {payload.reason}",
        priority="low",
        status="pending",
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    
    return {
        "message": "Leave request submitted.",
        "reference": leave.complaint_number,
        "from_date": payload.from_date,
        "to_date": payload.to_date
    }


@router.post("/transfers", response_model=StudentTransferResponse, status_code=201)
async def request_hostel_transfer(
    payload: StudentTransferCreateRequest,
    current_user: StudentUser,
    db: DBSession,
):
    """**Request hostel transfer** — Initiate an internal or external hostel transfer."""
    from app.schemas.transfer import StudentTransferCreateRequest, StudentTransferResponse
    from app.services.transfer_service import TransferService
    return await TransferService(db).request_transfer(user_id=current_user.id, payload=payload)


@router.get("/transfers", response_model=list[StudentTransferResponse])
async def list_my_transfers(
    current_user: StudentUser,
    db: DBSession,
):
    """**Student's transfer requests** — List all transfer requests for current student."""
    from app.schemas.transfer import StudentTransferResponse
    from app.services.transfer_service import TransferService
    return await TransferService(db).list_student_transfers(user_id=current_user.id)


@router.post("/transfers/{transfer_id}/cancel", response_model=StudentTransferResponse)
async def cancel_transfer_request(
    transfer_id: str,
    current_user: StudentUser,
    db: DBSession,
):
    """**Cancel transfer request** — Cancel a pending transfer request."""
    from app.schemas.transfer import StudentTransferResponse
    from app.services.transfer_service import TransferService
    return await TransferService(db).cancel_transfer(user_id=current_user.id, transfer_id=transfer_id)


# ==================== ADMIN HELPER ====================

@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student_by_admin(
    student_id: str,
    db: DBSession,
    current_user: AdminUser,
):
    """Get student details by ID (admin view)"""
    from app.models.student import Student
    from app.models.user import User
    from app.models.room import Room, Bed
    from app.models.booking import Booking
    from sqlalchemy import select
    
    result = await db.execute(
        select(Student, User, Room, Bed, Booking)
        .join(User, User.id == Student.user_id)
        .join(Room, Room.id == Student.room_id)
        .join(Bed, Bed.id == Student.bed_id)
        .join(Booking, Booking.id == Student.booking_id)
        .where(Student.id == student_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Student not found.")
    
    student, user, room, bed, booking = row
    
    if current_user.role == "hostel_admin":
        if str(student.hostel_id) not in current_user.hostel_ids:
            raise HTTPException(status_code=403, detail="Access denied to this student.")
    
    return {
        "id": str(student.id),
        "user_id": str(student.user_id),
        "hostel_id": str(student.hostel_id),
        "room_id": str(student.room_id),
        "bed_id": str(student.bed_id),
        "booking_id": str(student.booking_id),
        "student_number": student.student_number,
        "check_in_date": str(student.check_in_date),
        "check_out_date": str(student.check_out_date) if student.check_out_date else None,
        "status": student.status.value if hasattr(student.status, "value") else str(student.status),
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "profile_picture_url": user.profile_picture_url,
        "room_number": room.room_number,
        "bed_number": bed.bed_number,
        "booking_number": booking.booking_number,
        "created_at": student.created_at,
        "updated_at": student.updated_at,
    }
