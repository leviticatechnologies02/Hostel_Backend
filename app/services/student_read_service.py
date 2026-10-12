from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.student_read_repository import StudentReadRepository
from sqlalchemy import select
from app.models.hostel import Hostel
from app.models.room import Room, Bed
from app.models.booking import Booking
from app.services.booking_service import BookingService

class StudentReadService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = StudentReadRepository(session)

    async def get_profile(self, *, user_id: str):
        student = await self.repository.get_student_by_user(user_id)
        if student is None:
            return None
        
        # Get user
        user = await self.repository.get_user_by_id(user_id)
        if user is None:
            return None
        
        # Get hostel
        hostel_result = await self.repository.session.execute(
            select(Hostel).where(Hostel.id == student.hostel_id)
        )
        hostel = hostel_result.scalar_one_or_none()
        
        # Get room
        room_result = await self.repository.session.execute(
            select(Room).where(Room.id == student.room_id)
        )
        room = room_result.scalar_one_or_none()
        
        # Get bed
        bed_result = await self.repository.session.execute(
            select(Bed).where(Bed.id == student.bed_id)
        )
        bed = bed_result.scalar_one_or_none()
        
        # Get booking (includes gender!)
        booking_result = await self.repository.session.execute(
            select(Booking).where(Booking.id == student.booking_id)
        )
        booking = booking_result.scalar_one_or_none()
        
        return {
            "id": str(student.id),
            "user_id": str(student.user_id),
            "hostel_id": str(student.hostel_id),
            "room_id": str(student.room_id),
            "bed_id": str(student.bed_id),
            "booking_id": str(student.booking_id),
            "student_number": student.student_number,
            "check_in_date": student.check_in_date,
            "check_out_date": student.check_out_date,
            "status": student.status,
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
            "gender": booking.gender if booking else None,  # ← ADD THIS
            "date_of_birth": booking.date_of_birth if booking else None,  # ← ADD THIS (optional)
            "created_at": student.created_at,
            "updated_at": student.updated_at,
        }

    async def list_attendance(self, *, user_id: str):
        student = await self.repository.get_student_by_user(user_id)
        if student is None:
            return []
        return await self.repository.list_attendance(str(student.id))

    async def list_bookings(self, *, user_id: str):
        bookings = await self.repository.list_bookings_by_visitor(user_id)
        return [BookingService.booking_list_item(booking) for booking in bookings]

    async def list_notices(self, *, user_id: str):
        student = await self.repository.get_student_by_user(user_id)
        if student is None:
            return []
        return await self.repository.list_notices(str(student.hostel_id))

    async def list_mess_menus(self, *, user_id: str):
        student = await self.repository.get_student_by_user(user_id)
        if student is None:
            return []
        from app.services.mess_menu_service import _flatten_menus
        menus = await self.repository.list_mess_menus(str(student.hostel_id))
        return _flatten_menus(menus)

