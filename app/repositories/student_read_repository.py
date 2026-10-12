# app/repositories/student_read_repository.py
# Replace the get_profile method

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.operations import AttendanceRecord, MessMenu, Notice
from app.models.student import Student
from app.models.user import User
from app.models.hostel import Hostel
from app.models.room import Room, Bed


class StudentReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_student_by_user(self, user_id: str) -> Student | None:
        result = await self.session.execute(
            select(Student).where(Student.user_id == user_id).options(
                selectinload(Student.user),
                selectinload(Student.hostel),
                selectinload(Student.room),
                selectinload(Student.bed),
                selectinload(Student.booking)
            )
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_student_by_id(self, student_id: str) -> Student | None:
        """Get student by ID with all relations"""
        result = await self.session.execute(
            select(Student)
            .where(Student.id == student_id)
            .options(
                selectinload(Student.user),
                selectinload(Student.hostel),
                selectinload(Student.room),
                selectinload(Student.bed),
                selectinload(Student.booking)
            )
        )
        return result.scalar_one_or_none()

    async def list_attendance(self, student_id: str) -> list[AttendanceRecord]:
        result = await self.session.execute(
            select(AttendanceRecord)
            .where(AttendanceRecord.student_id == student_id)
            .order_by(AttendanceRecord.date.desc())
        )
        return list(result.scalars().all())

    async def list_bookings_by_visitor(self, user_id: str) -> list[Booking]:
        result = await self.session.execute(
            select(Booking)
            .options(
                selectinload(Booking.hostel),
                selectinload(Booking.room),
                selectinload(Booking.bed),
            )
            .where(Booking.visitor_id == user_id)
            .order_by(Booking.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_notices(self, hostel_id: str) -> list[Notice]:
        result = await self.session.execute(
            select(Notice)
            .where(
                or_(Notice.hostel_id == hostel_id, Notice.hostel_id.is_(None)),
                Notice.is_published.is_(True),
            )
            .order_by(Notice.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_mess_menus(self, hostel_id: str) -> list[MessMenu]:
        result = await self.session.execute(
            select(MessMenu)
            .options(selectinload(MessMenu.items))
            .where(MessMenu.hostel_id == hostel_id, MessMenu.is_active.is_(True))
            .order_by(MessMenu.week_start_date.desc())
        )
        return list(result.scalars().all())

    async def get_profile(self, *, user_id: str):
        """Get complete student profile with all related data including gender from booking"""
        from sqlalchemy.orm import joinedload
        
        # Query student with all relations loaded
        result = await self.session.execute(
            select(Student)
            .where(Student.user_id == user_id)
            .options(
                joinedload(Student.user),
                joinedload(Student.hostel),
                joinedload(Student.room),
                joinedload(Student.bed),
                joinedload(Student.booking)
            )
        )
        student = result.scalar_one_or_none()
        
        if student is None:
            return None
        
        # Get user
        user = student.user
        if user is None:
            return None
        
        # Get hostel
        hostel = student.hostel
        
        # Get room
        room = student.room
        
        # Get bed
        bed = student.bed
        
        # Get booking (includes gender!)
        booking = student.booking
        
        # Build response with all fields
        response = {
            "id": str(student.id),
            "user_id": str(student.user_id),
            "hostel_id": str(student.hostel_id) if student.hostel_id else None,
            "room_id": str(student.room_id) if student.room_id else None,
            "bed_id": str(student.bed_id) if student.bed_id else None,
            "booking_id": str(student.booking_id) if student.booking_id else None,
            "student_number": student.student_number,
            "check_in_date": student.check_in_date,
            "check_out_date": student.check_out_date,
            "status": student.status.value if hasattr(student.status, "value") else str(student.status),
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "profile_picture_url": user.profile_picture_url,
            "room_number": room.room_number if room else None,
            "bed_number": bed.bed_number if bed else None,
            "booking_number": booking.booking_number if booking else None,
            "booking_mode": booking.booking_mode.value if booking and hasattr(booking.booking_mode, "value") else None,
            "hostel_name": hostel.name if hostel else None,
            "hostel_city": hostel.city if hostel else None,
            "hostel_type": hostel.hostel_type.value if hostel and hasattr(hostel.hostel_type, "value") else None,
            "gender": booking.gender if booking else None,
            "date_of_birth": booking.date_of_birth if booking else None,
            "created_at": student.created_at,
            "updated_at": student.updated_at,
        }
        
        return response
