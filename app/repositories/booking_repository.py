from datetime import date, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import (
    BedStay,
    BedStayStatus,
    Booking,
    BookingStatus,
    BookingStatusHistory,
    WaitlistEntry,
    WaitlistStatus,
)
from app.models.room import Bed, BedStatus


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_booking(self, booking: Booking) -> Booking:
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def add_status_history(
        self,
        *,
        booking_id: str,
        old_status: BookingStatus | None,
        new_status: BookingStatus,
        changed_by: str | None,
        note: str | None = None,
    ) -> None:
        self.session.add(
            BookingStatusHistory(
                booking_id=booking_id,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                note=note,
            )
        )
        await self.session.flush()

    async def get_by_id(self, booking_id: str) -> Booking | None:
        result = await self.session.execute(select(Booking).where(Booking.id == booking_id))
        return result.scalar_one_or_none()

    async def list_by_hostel(self, hostel_id: str) -> list[Booking]:
        result = await self.session.execute(
            select(Booking).where(Booking.hostel_id == hostel_id).order_by(Booking.created_at.desc())
        )
        return list(result.scalars().all())

    async def has_overlap(self, *, bed_id: str, start_date: datetime, end_date: datetime, exclude_booking_id: str | None = None) -> bool:
        """
        Check if there's an overlapping BedStay for the given bed and dates.
        """
        from datetime import datetime as dt_datetime
        from sqlalchemy import case, func

        today = func.now()

        effective_end_date = case(
            (BedStay.status == BedStayStatus.ACTIVE, func.greatest(BedStay.end_date, today)),
            else_=BedStay.end_date
        )

        query = select(BedStay.id).where(
            BedStay.bed_id == bed_id,
            BedStay.status.in_([BedStayStatus.RESERVED, BedStayStatus.ACTIVE]),
            # Overlap condition: start1 < end2 AND end1 > start2
            BedStay.start_date < end_date,
            effective_end_date > start_date,
        )
        
        # Exclude self when updating an existing booking
        if exclude_booking_id:
            query = query.where(BedStay.booking_id != exclude_booking_id)
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
    
    async def is_bed_available(self, *, bed_id: str, start_date: datetime, end_date: datetime) -> bool:
        """
        Check if a bed is available for the given date range.
        
        This is the public-facing availability check used during booking creation.
        
        Returns:
            True if bed is available, False otherwise
        """
        has_overlap = await self.has_overlap(bed_id=bed_id, start_date=start_date, end_date=end_date)
        return not has_overlap
    
    async def get_available_beds(
        self,
        *,
        hostel_id: str,
        room_id: str | None = None,
        start_date: date | datetime,
        end_date: date | datetime,
    ) -> list[Bed]:
        """
        Get all available beds for the given date range using a single NOT EXISTS query.
        No N+1 — one query total.
        """
        from sqlalchemy import not_, exists, case, func

        effective_end_date = case(
            (BedStay.status == BedStayStatus.ACTIVE, func.greatest(BedStay.end_date, func.now())),
            else_=BedStay.end_date
        )

        occupied_subq = (
            select(BedStay.bed_id)
            .where(
                BedStay.status.in_([BedStayStatus.RESERVED, BedStayStatus.ACTIVE]),
                BedStay.start_date < end_date,
                effective_end_date > start_date,
            )
            .correlate(Bed)
            .where(BedStay.bed_id == Bed.id)
        )

        query = select(Bed).where(
            Bed.hostel_id == hostel_id,
            Bed.status != BedStatus.MAINTENANCE,
            not_(exists(occupied_subq)),
        )
        if room_id:
            query = query.where(Bed.room_id == room_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_bed_stay(
        self,
        *,
        hostel_id: str,
        bed_id: str,
        booking_id: str,
        start_date: date,
        end_date: date,
        status: BedStayStatus,
    ) -> BedStay:
        bed_stay = BedStay(
            hostel_id=hostel_id,
            bed_id=bed_id,
            booking_id=booking_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )
        self.session.add(bed_stay)
        await self.session.flush()
        return bed_stay

    async def get_active_waitlist_entry(
        self,
        *,
        visitor_id: str,
        room_id: str,
        check_in_date: date,
        check_out_date: date,
    ) -> WaitlistEntry | None:
        """Get active waitlist entry for visitor and room"""
        try:
            result = await self.session.execute(
                select(WaitlistEntry).where(
                    WaitlistEntry.visitor_id == visitor_id,
                    WaitlistEntry.room_id == room_id,
                    WaitlistEntry.status == WaitlistStatus.ACTIVE,
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            print(f"Error getting active waitlist entry: {e}")
            return None

    async def create_waitlist_entry(self, entry: WaitlistEntry) -> WaitlistEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry


    async def get_waitlist_position(self, *, entry: WaitlistEntry) -> int:
        """Get 1-indexed position in waitlist queue"""
        try:
            result = await self.session.execute(
                select(func.count())
                .select_from(WaitlistEntry)
                .where(
                    WaitlistEntry.room_id == entry.room_id,
                    WaitlistEntry.status == WaitlistStatus.ACTIVE,
                    WaitlistEntry.created_at <= entry.created_at,
                )
            )
            return int(result.scalar() or 0)
        except Exception as e:
            print(f"Error in get_waitlist_position: {e}")
            return 1  # Default to position 1

    async def list_waitlist_entries_by_visitor(self, visitor_id: str) -> list[WaitlistEntry]:
        """List all waitlist entries for a visitor"""
        # Remove the problematic selectinload
        result = await self.session.execute(
            select(WaitlistEntry) 
            .where(
                WaitlistEntry.visitor_id == visitor_id,
                WaitlistEntry.status.in_([WaitlistStatus.ACTIVE, WaitlistStatus.NOTIFIED])
            )
            .order_by(WaitlistEntry.created_at.desc())
        )
        return list(result.scalars().all())




    async def get_waitlist_entry_by_id(self, entry_id: str) -> WaitlistEntry | None:
        """Get waitlist entry by ID"""
        result = await self.session.execute(
            select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
        )
        return result.scalar_one_or_none()
