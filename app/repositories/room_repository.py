from datetime import date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import BedStay, BedStayStatus
from app.models.room import Bed, Room, BedStatus


class RoomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_hostel(self, hostel_id: str) -> list[Room]:
        result = await self.session.execute(
            select(Room)
            .where(Room.hostel_id == hostel_id, Room.is_active.is_(True))
            .order_by(Room.floor, Room.room_number)
        )
        return list(result.scalars().all())

    async def get_by_id(self, room_id: str) -> Room | None:
        result = await self.session.execute(select(Room).where(Room.id == room_id))
        return result.scalar_one_or_none()

    async def get_available_bed_count(
        self, room_id: str, start_date: date | datetime, end_date: date | datetime
    ) -> int:
        total_result = await self.session.execute(
            select(func.count())
            .select_from(Bed)
            .where(
                Bed.room_id == room_id,
                Bed.status != BedStatus.MAINTENANCE,
            )
        )
        total = int(total_result.scalar_one() or 0)

        effective_end_date = case(
            (
                BedStay.status == BedStayStatus.ACTIVE,
                func.greatest(BedStay.end_date, func.now()),
            ),
            else_=BedStay.end_date,
        )
        occupied_result = await self.session.execute(
            select(func.count(func.distinct(BedStay.bed_id)))
            .select_from(BedStay)
            .join(Bed, Bed.id == BedStay.bed_id)
            .where(
                Bed.room_id == room_id,
                BedStay.status.in_([BedStayStatus.RESERVED, BedStayStatus.ACTIVE]),
                BedStay.start_date < end_date,
                effective_end_date > start_date,
            )
        )
        occupied = int(occupied_result.scalar_one() or 0)

        return max(0, total - occupied)
