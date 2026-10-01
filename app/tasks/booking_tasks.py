"""
Background booking lifecycle tasks.
"""
from datetime import UTC, datetime

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking, BookingMode, BookingStatus
from app.repositories.booking_repository import BookingRepository


@celery_app.task(bind=True, max_retries=3, ignore_result=True)
def expire_draft_booking_task(self, booking_id: str):
    """
    Expire a DRAFT booking after 30 minutes if still unpaid.
    """
    import asyncio
    
    async def _run():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Booking).where(Booking.id == booking_id))
            booking = result.scalar_one_or_none()
            if booking is None:
                return
            if booking.status != BookingStatus.DRAFT:
                return

            # Guard against race: only expire drafts older than 30 mins
            age_seconds = (datetime.now(UTC) - booking.created_at).total_seconds()
            if age_seconds < 30 * 60:
                return

            old_status = booking.status
            booking.status = BookingStatus.CANCELLED
            booking.cancellation_reason = "Draft booking expired after 30 minutes."

            repo = BookingRepository(session)
            await repo.add_status_history(
                booking_id=str(booking.id),
                old_status=old_status,
                new_status=BookingStatus.CANCELLED,
                changed_by=None,
                note="Auto-expired draft booking after 30 minutes.",
            )
            await session.commit()

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


async def auto_checkout_expired_bookings():
    """
    Auto-checkout expired daily/hourly bookings whose check_out_date has passed.

    This releases the bed (Bed.status → AVAILABLE), marks the BedStay as COMPLETED,
    updates booking status to CHECKED_OUT, and marks the student as CHECKED_OUT.

    Should be called periodically (e.g., every 5 minutes) from a background loop.
    """
    import logging

    from app.models.booking import BedStay, BedStayStatus
    from app.models.room import Bed, BedStatus
    from app.models.student import Student, StudentStatus

    logger = logging.getLogger("auto_checkout")

    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(UTC)

            # Find all CHECKED_IN bookings that are daily or hourly
            # and whose check_out_date has passed
            result = await session.execute(
                select(Booking).where(
                    Booking.status == BookingStatus.CHECKED_IN,
                    Booking.booking_mode.in_([BookingMode.DAILY, BookingMode.HOURLY]),
                    Booking.check_out_date <= now,
                )
            )
            expired_bookings = result.scalars().all()

            if not expired_bookings:
                return 0

            count = 0
            for booking in expired_bookings:
                old_status = booking.status
                booking.status = BookingStatus.CHECKED_OUT

                # Mark BedStay as COMPLETED
                bed_stay_result = await session.execute(
                    select(BedStay).where(
                        BedStay.booking_id == str(booking.id),
                        BedStay.status == BedStayStatus.ACTIVE,
                    )
                )
                bed_stay = bed_stay_result.scalar_one_or_none()
                if bed_stay:
                    bed_stay.status = BedStayStatus.COMPLETED

                # Release the bed → AVAILABLE
                if booking.bed_id:
                    bed = await session.get(Bed, booking.bed_id)
                    if bed and bed.status == BedStatus.OCCUPIED:
                        # Check if there's another active booking on this bed
                        other_active = await session.execute(
                            select(Booking.id).where(
                                Booking.bed_id == booking.bed_id,
                                Booking.status == BookingStatus.CHECKED_IN,
                                Booking.id != str(booking.id),
                            )
                        )
                        if not other_active.scalars().first():
                            bed.status = BedStatus.AVAILABLE

                # Mark the student record as CHECKED_OUT
                student_result = await session.execute(
                    select(Student).where(
                        Student.booking_id == str(booking.id),
                        Student.status == StudentStatus.ACTIVE,
                    )
                )
                student = student_result.scalar_one_or_none()
                if student:
                    student.status = StudentStatus.CHECKED_OUT
                    student.check_out_date = now.date()

                # Add status history
                repo = BookingRepository(session)
                await repo.add_status_history(
                    booking_id=str(booking.id),
                    old_status=old_status,
                    new_status=BookingStatus.CHECKED_OUT,
                    changed_by=None,
                    note=f"Auto-checkout: {booking.booking_mode.value} booking expired at {booking.check_out_date}.",
                )

                count += 1
                logger.info(
                    f"Auto-checked out booking {booking.booking_number} "
                    f"(mode={booking.booking_mode.value}, checkout={booking.check_out_date})"
                )

            await session.commit()
            if count > 0:
                logger.info(f"Auto-checkout complete: {count} expired booking(s) processed.")
            return count

    except Exception:
        logger.exception("Error in auto_checkout_expired_bookings")
        return 0


@celery_app.task(bind=True, max_retries=2, ignore_result=True)
def auto_checkout_expired_bookings_celery(self):
    """
    Celery wrapper for auto_checkout_expired_bookings.
    Scheduled via Celery beat to run every 5 minutes.
    """
    import asyncio

    try:
        asyncio.run(auto_checkout_expired_bookings())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)