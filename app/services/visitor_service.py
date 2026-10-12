from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.visitor_repository import VisitorRepository
from app.services.booking_service import BookingService


class VisitorService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = VisitorRepository(session)

    async def list_bookings(self, visitor_id: str):
        bookings = await self.repository.list_bookings(visitor_id)
        return [BookingService.booking_list_item(booking) for booking in bookings]
