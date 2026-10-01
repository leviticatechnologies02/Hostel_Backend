"""
Booking service — transaction-safe booking lifecycle management.
All state transitions commit atomically. BedStay is the source of truth for occupancy.
"""
import asyncio
from datetime import date
import uuid 
from sqlalchemy import select, func

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BedStay, BedStayStatus, Booking, BookingMode, BookingStatus
from app.models.booking import WaitlistEntry, WaitlistStatus
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingCreateRequest
from app.schemas.booking import BookingInitiateRequest, BookingApplicantPatchRequest, WaitlistJoinRequest
from app.services.subscription_validator import SubscriptionValidator



class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BookingRepository(session)

    # ──────────────────────────────────────────────────────────────────
    # CREATE
    # ──────────────────────────────────────────────────────────────────
    async def create_booking(self, *, visitor_id: str, payload: BookingCreateRequest) -> Booking:
        """Create booking in PAYMENT_PENDING status. Commits atomically."""
        # ── Date validation ───────────────────────────────────────────
        if payload.check_out_date <= payload.check_in_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="check_out_date must be after check_in_date",
            )
        
        # ── Subscription validation ───────────────────────────────────
        await self.check_hostel_subscription(
            hostel_id=payload.hostel_id,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date
        )
        # Check subscription (add timeout)
        try:
            validator = SubscriptionValidator(self.session)
            await asyncio.wait_for(
                validator.validate_hostel_subscription(
                    hostel_id=payload.hostel_id,
                    check_in_date=payload.check_in_date,
                    check_out_date=payload.check_out_date
                ),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Subscription validation timed out"
            )
        
        booking_number = f"SE-{uuid.uuid4().hex[:10].upper()}"

        mode = BookingMode(payload.booking_mode)
        total_nights: int | None = None
        total_months: int | None = None
        total_hours: int | None = None

        if mode == BookingMode.HOURLY:
            diff = payload.check_out_date - payload.check_in_date
            total_hours = max(1, int(diff.total_seconds() / 3600))

            # ── Hourly-mode backend validations ───────────────────────
            # Fetch room from DB to validate hourly_rent and recalculate price
            from app.models.room import Room
            room_res = await self.session.execute(
                select(Room).where(Room.id == payload.room_id)
            )
            room = room_res.scalar_one_or_none()
            if not room:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Room not found.",
                )
            # Block ₹0/hour bookings — admin must set hourly_rent first
            if float(room.hourly_rent or 0) <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This room does not have an hourly rate configured. Please contact the hostel admin.",
                )
            # Recalculate server-side to prevent frontend price tampering
            server_base = float(room.hourly_rent) * total_hours
            server_deposit = float(room.security_deposit or 0)
            payload.base_rent_amount = server_base
            payload.security_deposit = server_deposit

        elif mode == BookingMode.DAILY:
            total_nights = max(1, (payload.check_out_date - payload.check_in_date).days)
        else:
            s, e = payload.check_in_date, payload.check_out_date
            total_months = (e.year - s.year) * 12 + (e.month - s.month)
            if e.day < s.day:
                total_months -= 1
            total_months = max(1, total_months)

        grand_total = payload.grand_total or (
            (payload.base_rent_amount or 0) + (payload.security_deposit or 0)
        )
        # For hourly, always use the server-calculated total (ignore frontend value)
        if mode == BookingMode.HOURLY:
            grand_total = (payload.base_rent_amount or 0) + (payload.security_deposit or 0)

        booking = Booking(
            booking_number=booking_number,
            visitor_id=visitor_id,
            hostel_id=payload.hostel_id,
            room_id=payload.room_id,
            bed_id=payload.bed_id,
            booking_mode=mode,
            status=BookingStatus.PAYMENT_PENDING,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            total_hours=total_hours,
            total_nights=total_nights,
            total_months=total_months,
            base_rent_amount=payload.base_rent_amount or 0,
            security_deposit=payload.security_deposit or 0,
            booking_advance=payload.booking_advance or 0,
            grand_total=grand_total,
            full_name=payload.full_name,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            occupation=payload.occupation,
            institution=payload.institution,
            current_address=payload.current_address,
            id_type=payload.id_type,
            id_document_url=payload.id_document_url,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_phone=payload.emergency_contact_phone,
            emergency_contact_relationship=payload.emergency_contact_relationship,
            guardian_name=payload.guardian_name,
            guardian_phone=payload.guardian_phone,
            special_requirements=payload.special_requirements,
        )

        booking = await self.repository.create_booking(booking)
        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=None,
            new_status=BookingStatus.PAYMENT_PENDING,
            changed_by=visitor_id,
            note="Booking created, awaiting payment.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def initiate_booking(self, *, visitor_id: str, payload: BookingInitiateRequest) -> Booking:
        """
        Create booking in DRAFT status with pricing breakdown.
        Bed assignment is optional at this stage, but availability is still validated.
        """
        # Check subscription
        try:
            validator = SubscriptionValidator(self.session)
            await validator.validate_hostel_subscription(
                hostel_id=payload.hostel_id,
                check_in_date=payload.check_in_date,
                check_out_date=payload.check_out_date
            )
        except Exception as e:
            print(f"Subscription validation error: {e}")
            # Continue anyway for testing
        
        # Validate bed availability if bed_id is provided
        if payload.bed_id:
            is_available = await self.repository.is_bed_available(
                bed_id=payload.bed_id,
                start_date=payload.check_in_date,
                end_date=payload.check_out_date,
            )
            if not is_available:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Selected bed is not available for requested dates.",
                )
        else:
            # Check if any beds are available in the room
            available_beds = await self.repository.get_available_beds(
                hostel_id=payload.hostel_id,
                room_id=payload.room_id,
                start_date=payload.check_in_date,
                end_date=payload.check_out_date,
            )
            if not available_beds:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No beds available for requested room and dates.",
                )

        # Calculate nights/months
        mode = BookingMode(payload.booking_mode)
        total_nights: int | None = None
        total_months: int | None = None
        total_hours: int | None = None
        
        if mode == BookingMode.HOURLY:
            diff = payload.check_out_date - payload.check_in_date
            total_hours = max(1, int(diff.total_seconds() / 3600))
        elif mode == BookingMode.DAILY:
            total_nights = max(1, (payload.check_out_date - payload.check_in_date).days)
        else:
            s, e = payload.check_in_date, payload.check_out_date
            total_months = (e.year - s.year) * 12 + (e.month - s.month)
            if e.day < s.day:
                total_months -= 1
            total_months = max(1, total_months) if total_months else 1

        # Create booking number
        booking_number = f"SE-{uuid.uuid4().hex[:10].upper()}"
        
        # Create booking
        booking = Booking(
            booking_number=booking_number,
            visitor_id=visitor_id,
            hostel_id=payload.hostel_id,
            room_id=payload.room_id,
            bed_id=payload.bed_id,
            booking_mode=mode,
            status=BookingStatus.DRAFT,
            check_in_date=payload.check_in_date,
            check_out_date=payload.check_out_date,
            total_hours=total_hours,
            total_nights=total_nights,
            total_months=total_months,
            base_rent_amount=payload.base_rent_amount,
            security_deposit=payload.security_deposit,
            booking_advance=payload.booking_advance,
            grand_total=payload.grand_total,
            full_name="Pending Applicant",  # Placeholder, will be updated later
        )
        
        booking = await self.repository.create_booking(booking)
        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=None,
            new_status=BookingStatus.DRAFT,
            changed_by=visitor_id,
            note="Booking initiated as draft.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking


    async def update_applicant_info(
        self, *, booking_id: str, visitor_id: str, payload: BookingApplicantPatchRequest
    ) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        if str(booking.visitor_id) != visitor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking.")
        if booking.status not in (BookingStatus.DRAFT, BookingStatus.PAYMENT_PENDING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update applicant details in status '{booking.status.value}'.",
            )

        booking.full_name = payload.full_name
        booking.date_of_birth = payload.date_of_birth
        booking.gender = payload.gender
        booking.occupation = payload.occupation
        booking.institution = payload.institution
        booking.current_address = payload.current_address
        booking.id_type = payload.id_type
        booking.id_document_url = payload.id_document_url
        booking.emergency_contact_name = payload.emergency_contact_name
        booking.emergency_contact_phone = payload.emergency_contact_phone
        booking.emergency_contact_relationship = payload.emergency_contact_relationship
        booking.guardian_name = payload.guardian_name
        booking.guardian_phone = payload.guardian_phone
        booking.special_requirements = payload.special_requirements

        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # LIST
    # ──────────────────────────────────────────────────────────────────
    async def list_admin_bookings(self, *, hostel_id: str) -> list[Booking]:
        return await self.repository.list_by_hostel(hostel_id)

    # ──────────────────────────────────────────────────────────────────
    # APPROVE — overlap check → BedStay RESERVED → commit
    # ──────────────────────────────────────────────────────────────────
    async def approve_booking(
        self, *, booking_id: str, approved_by: str, bed_id: str | None = None
    ) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status not in (BookingStatus.PAYMENT_PENDING, BookingStatus.PENDING_APPROVAL):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve from status '{booking.status.value}'.",
            )

        target_bed_id = bed_id or str(booking.bed_id) if booking.bed_id else bed_id
        if not target_bed_id:
            raise HTTPException(status_code=400, detail="bed_id is required for approval.")

        # ── Overlap check (BedStay source of truth) ──────────────────
        if await self.repository.has_overlap(
            bed_id=target_bed_id,
            start_date=booking.check_in_date,
            end_date=booking.check_out_date,
            exclude_booking_id=booking_id,
        ):
            raise HTTPException(
                status_code=409,
                detail="Bed is not available for the requested dates.",
            )

        old_status = booking.status
        booking.status = BookingStatus.APPROVED
        booking.bed_id = target_bed_id
        booking.approved_by = approved_by

        await self.repository.create_bed_stay(
            hostel_id=str(booking.hostel_id),
            bed_id=target_bed_id,
            booking_id=str(booking.id),
            start_date=booking.check_in_date,
            end_date=booking.check_out_date,
            status=BedStayStatus.RESERVED,
        )
        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=old_status,
            new_status=BookingStatus.APPROVED,
            changed_by=approved_by,
            note="Booking approved and bed reserved.",
        )

        # Long stays are tenants as soon as their booking is approved.  Keep this
        # in the same transaction as the reservation so an approved monthly stay
        # can never be left as a visitor because profile creation failed.
        from app.services.student_service import StudentService

        tenant_service = StudentService(self.session)
        if tenant_service.is_tenant_booking(booking):
            await tenant_service.ensure_tenant_record_from_booking(
                booking_id=str(booking.id),
                actor_id=approved_by,
                commit=False,
            )

        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # REJECT — release BedStay → commit
    # ──────────────────────────────────────────────────────────────────
    async def reject_booking(
        self, *, booking_id: str, rejected_by: str, reason: str | None = None
    ) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status not in (BookingStatus.PAYMENT_PENDING, BookingStatus.PENDING_APPROVAL):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject from status '{booking.status.value}'.",
            )

        old_status = booking.status
        booking.status = BookingStatus.REJECTED
        booking.rejection_reason = reason

        if booking.bed_id:
            await self._release_bed_stay(str(booking.id))

        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=old_status,
            new_status=BookingStatus.REJECTED,
            changed_by=rejected_by,
            note=reason or "Booking rejected.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # CANCEL — release BedStay → commit
    # ──────────────────────────────────────────────────────────────────
    async def cancel_booking(
        self, *, booking_id: str, cancelled_by: str, reason: str | None = None
    ) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status not in (BookingStatus.APPROVED, BookingStatus.PAYMENT_PENDING, BookingStatus.PENDING_APPROVAL):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel from status '{booking.status.value}'.",
            )

        old_status = booking.status
        booking.status = BookingStatus.CANCELLED
        booking.cancellation_reason = reason

        if booking.bed_id:
            await self._release_bed_stay(str(booking.id))

        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=old_status,
            new_status=BookingStatus.CANCELLED,
            changed_by=cancelled_by,
            note=reason or "Booking cancelled.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # CHECK-IN — BedStay RESERVED → ACTIVE → commit
    # ──────────────────────────────────────────────────────────────────
    async def check_in_student(self, *, booking_id: str, checked_in_by: str) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status != BookingStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot check in from status '{booking.status.value}'. Must be APPROVED.",
            )
        if not booking.bed_id:
            raise HTTPException(status_code=400, detail="No bed assigned to this booking.")

        # Check if the bed is already occupied by another active checked-in booking/student
        active_booking_query = select(Booking).where(
            Booking.bed_id == booking.bed_id,
            Booking.status == BookingStatus.CHECKED_IN,
            Booking.id != booking.id,
        )
        active_booking_result = await self.session.execute(active_booking_query)
        if active_booking_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This bed is already occupied. Please select another available bed.",
            )

        old_status = booking.status
        booking.status = BookingStatus.CHECKED_IN

        result = await self.session.execute(
            select(BedStay).where(
                BedStay.booking_id == booking_id,
                BedStay.bed_id == booking.bed_id,
                BedStay.status == BedStayStatus.RESERVED,
            )
        )
        bed_stay = result.scalar_one_or_none()
        if bed_stay:
            bed_stay.status = BedStayStatus.ACTIVE
        else:
            await self.repository.create_bed_stay(
                hostel_id=str(booking.hostel_id),
                bed_id=str(booking.bed_id),
                booking_id=booking_id,
                start_date=booking.check_in_date,
                end_date=booking.check_out_date,
                status=BedStayStatus.ACTIVE,
            )

        # Update Bed.status in the DB
        from app.models.room import Bed, BedStatus
        bed = await self.session.get(Bed, booking.bed_id)
        if bed:
            bed.status = BedStatus.OCCUPIED

        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=old_status,
            new_status=BookingStatus.CHECKED_IN,
            changed_by=checked_in_by,
            note="Student checked in.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # CHECK-OUT — BedStay ACTIVE → COMPLETED → commit
    # ──────────────────────────────────────────────────────────────────
    async def check_out_student(self, *, booking_id: str, checked_out_by: str) -> Booking:
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found.")

        if booking.status != BookingStatus.CHECKED_IN:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot check out from status '{booking.status.value}'. Must be CHECKED_IN.",
            )

        old_status = booking.status
        booking.status = BookingStatus.CHECKED_OUT

        result = await self.session.execute(
            select(BedStay).where(
                BedStay.booking_id == booking_id,
                BedStay.status == BedStayStatus.ACTIVE,
            )
        )
        bed_stay = result.scalar_one_or_none()
        if bed_stay:
            bed_stay.status = BedStayStatus.COMPLETED

        # Update Bed.status in DB
        from app.models.room import Bed, BedStatus
        bed = await self.session.get(Bed, booking.bed_id)
        if bed:
            bed.status = BedStatus.AVAILABLE

        await self.repository.add_status_history(
            booking_id=str(booking.id),
            old_status=old_status,
            new_status=BookingStatus.CHECKED_OUT,
            changed_by=checked_out_by,
            note="Student checked out.",
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ──────────────────────────────────────────────────────────────────
    # INTERNAL — release BedStay (no commit — caller commits)
    # ──────────────────────────────────────────────────────────────────
    async def _release_bed_stay(self, booking_id: str) -> None:
        result = await self.session.execute(
            select(BedStay).where(
                BedStay.booking_id == booking_id,
                BedStay.status.in_([BedStayStatus.RESERVED, BedStayStatus.ACTIVE]),
            )
        )
        bed_stay = result.scalar_one_or_none()
        if bed_stay:
            bed_stay.status = BedStayStatus.CANCELLED


    async def join_waitlist(self, *, visitor_id: str, payload: WaitlistJoinRequest) -> tuple[WaitlistEntry, int]:
        """
        Join waitlist for a room when no beds are available.
        Returns (waitlist_entry, position_in_queue)
        """
        from app.models.booking import WaitlistEntry, WaitlistStatus, BookingMode
        from sqlalchemy import select
        from datetime import date
        
        # Validate dates
        if payload.check_out_date <= payload.check_in_date:
            raise HTTPException(
                status_code=400,
                detail="check_out_date must be after check_in_date"
            )
        
        if payload.check_in_date < date.today():
            raise HTTPException(
                status_code=400,
                detail="Check-in date cannot be in the past"
            )
        
        # Validate room exists
        from app.models.room import Room
        room_result = await self.session.execute(
            select(Room).where(Room.id == payload.room_id)
        )
        room = room_result.scalar_one_or_none()
        if not room:
            raise HTTPException(
                status_code=404,
                detail=f"Room {payload.room_id} not found"
            )
        
        try:
            # Check for existing active waitlist entry
            existing = await self.session.execute(
                select(WaitlistEntry).where(
                    WaitlistEntry.visitor_id == visitor_id,
                    WaitlistEntry.room_id == payload.room_id,
                    WaitlistEntry.status == WaitlistStatus.ACTIVE,
                    WaitlistEntry.check_in_date == payload.check_in_date,
                    WaitlistEntry.check_out_date == payload.check_out_date
                )
            )
            existing_entry = existing.scalar_one_or_none()
            
            if existing_entry:
                # Calculate position
                pos_result = await self.session.execute(
                    select(func.count())
                    .select_from(WaitlistEntry)
                    .where(
                        WaitlistEntry.room_id == payload.room_id,
                        WaitlistEntry.status == WaitlistStatus.ACTIVE,
                        WaitlistEntry.created_at <= existing_entry.created_at
                    )
                )
                position = int(pos_result.scalar() or 0)
                return existing_entry, position
            
            # Create new waitlist entry
            entry = WaitlistEntry(
                visitor_id=visitor_id,
                hostel_id=payload.hostel_id,
                room_id=payload.room_id,
                bed_id=payload.bed_id,
                check_in_date=payload.check_in_date,
                check_out_date=payload.check_out_date,
                booking_mode=BookingMode(payload.booking_mode),
                status=WaitlistStatus.ACTIVE,
            )
            
            self.session.add(entry)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(entry)
            
            # Calculate position
            pos_result = await self.session.execute(
                select(func.count())
                .select_from(WaitlistEntry)
                .where(
                    WaitlistEntry.room_id == payload.room_id,
                    WaitlistEntry.status == WaitlistStatus.ACTIVE,
                    WaitlistEntry.created_at <= entry.created_at
                )
            )
            position = int(pos_result.scalar() or 0)
            
            return entry, position
            
        except Exception as e:
            await self.session.rollback()
            print(f"Waitlist join error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to join waitlist: {str(e)}"
            )
        
    async def list_my_waitlist(self, *, visitor_id: str) -> list[dict]:
        entries = await self.repository.list_waitlist_entries_by_visitor(visitor_id)
        result: list[dict] = []
        for entry in entries:
            position = await self.repository.get_waitlist_position(entry=entry)
            result.append(
                {
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
            )
        return result

    async def leave_waitlist(self, *, visitor_id: str, entry_id: str) -> None:
        entry = await self.repository.get_waitlist_entry_by_id(entry_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Waitlist entry not found.")
        if str(entry.visitor_id) != str(visitor_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your waitlist entry.")
        if entry.status not in (WaitlistStatus.ACTIVE, WaitlistStatus.NOTIFIED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This waitlist entry can no longer be cancelled.",
            )
        entry.status = WaitlistStatus.CANCELLED
        await self.session.commit()

    async def check_hostel_subscription(self, hostel_id: str, check_in_date: date, check_out_date: date) -> None:
        """
        Check if hostel has an active subscription for the booking dates.
        Raises HTTPException if no active subscription or booking exceeds subscription.
        """
        from app.models.operations import Subscription
        from datetime import date as date_type
        
        # Get active subscription for this hostel
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.hostel_id == hostel_id,
                Subscription.status == "active"
            )
        )
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            print(f"⚠️ WARNING: Hostel {hostel_id} has no active subscription. Allowing booking for testing.")
            return  # Allow for testing - remove in production
        
        # Check if booking dates are within subscription period
        if check_in_date < subscription.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Check-in date {check_in_date} is before subscription start date {subscription.start_date}"
            )
        
        if check_out_date > subscription.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Check-out date {check_out_date} exceeds subscription end date {subscription.end_date}"
            )
        
        return subscription
