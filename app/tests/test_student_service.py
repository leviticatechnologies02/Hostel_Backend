from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.booking import BookingMode, BookingStatus
from app.services.student_service import StudentService


@pytest.mark.asyncio
async def test_check_in_rejects_non_approved_booking() -> None:
    session = AsyncMock()
    service = StudentService(session)
    service.booking_repository = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id="booking-1",
                status=BookingStatus.PENDING_APPROVAL,
                bed_id="bed-1",
            )
        )
    )

    with pytest.raises(HTTPException) as exc:
        await service.check_in_from_booking(booking_id="booking-1", actor_id="admin-1")

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_approved_monthly_booking_creates_tenant_record() -> None:
    session = AsyncMock()
    service = StudentService(session)
    booking = SimpleNamespace(
        id="booking-1",
        status=BookingStatus.APPROVED,
        booking_mode=BookingMode.MONTHLY,
        total_nights=None,
        bed_id="bed-1",
        visitor_id="user-1",
        hostel_id="hostel-1",
        room_id="room-1",
        check_in_date=None,
    )
    student = SimpleNamespace(id="student-1")
    service.booking_repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=booking),
        add_status_history=AsyncMock(),
    )
    service.student_repository = SimpleNamespace(
        get_student_by_booking=AsyncMock(return_value=None),
        create_from_booking=AsyncMock(return_value=student),
        activate_bed_stay=AsyncMock(),
        link_bed_stay_to_student=AsyncMock(),
        promote_user_to_student=AsyncMock(),
        set_booking_checked_in=AsyncMock(),
    )

    result = await service.check_in_from_booking(booking_id="booking-1", actor_id="admin-1")

    assert result is student
    service.student_repository.create_from_booking.assert_awaited_once()
    service.student_repository.link_bed_stay_to_student.assert_awaited_once()
    service.student_repository.promote_user_to_student.assert_awaited_once_with("user-1")


def test_daily_tenant_threshold_is_more_than_ten_nights() -> None:
    ten_nights = SimpleNamespace(
        booking_mode=BookingMode.DAILY,
        total_nights=10,
        check_in_date=None,
        check_out_date=None,
    )
    eleven_nights = SimpleNamespace(
        booking_mode=BookingMode.DAILY,
        total_nights=11,
        check_in_date=None,
        check_out_date=None,
    )

    assert StudentService.is_tenant_booking(ten_nights) is False
    assert StudentService.is_tenant_booking(eleven_nights) is True
