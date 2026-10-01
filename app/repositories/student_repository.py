from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BedStay, BedStayStatus, Booking, BookingStatus
from app.models.student import Student, StudentStatus
from app.models.user import User, UserRole


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_student_by_booking(self, booking_id: str) -> Student | None:
        result = await self.session.execute(select(Student).where(Student.booking_id == booking_id))
        return result.scalar_one_or_none()

    async def create_from_booking(self, *, booking: Booking) -> Student:
        student = Student(
            user_id=booking.visitor_id,
            hostel_id=booking.hostel_id,
            room_id=booking.room_id,
            bed_id=booking.bed_id,
            booking_id=booking.id,
            student_number=f"STU-{str(booking.id)[:8].upper()}",
            check_in_date=booking.check_in_date,
            status=StudentStatus.ACTIVE,
        )
        self.session.add(student)
        await self.session.flush()
        return student

    async def set_booking_checked_in(self, booking: Booking) -> None:
        booking.status = BookingStatus.CHECKED_IN
        await self.session.flush()

    async def activate_bed_stay(self, booking_id: str, student_id: str) -> BedStay | None:
        result = await self.session.execute(select(BedStay).where(BedStay.booking_id == booking_id))
        bed_stay = result.scalar_one_or_none()
        if bed_stay is not None:
            bed_stay.student_id = student_id
            bed_stay.status = BedStayStatus.ACTIVE
        await self.session.flush()
        return bed_stay

    async def link_bed_stay_to_student(self, booking_id: str, student_id: str) -> BedStay | None:
        """Attach a reserved stay to a tenant without marking it occupied yet."""
        result = await self.session.execute(select(BedStay).where(BedStay.booking_id == booking_id))
        bed_stay = result.scalar_one_or_none()
        if bed_stay is not None:
            bed_stay.student_id = student_id
        await self.session.flush()
        return bed_stay

    async def promote_user_to_student(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is not None:
            user.role = UserRole.STUDENT  # ← Promotes visitor to student
        return user
