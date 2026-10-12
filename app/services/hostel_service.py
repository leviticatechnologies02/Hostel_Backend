# Replace the full file: app/services/hostel_service.py

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hostel import Hostel, HostelAmenity
from app.models.operations import Review
from app.models.room import Room
from app.repositories.hostel_repository import HostelRepository
from app.repositories.room_repository import RoomRepository


def _build_hostel_dict(
    hostel: Hostel,
    avg_rating: float,
    review_count: int,
    starting_monthly_price: float,
    starting_daily_price: float,
    available_beds: int,
) -> dict:
    return {
        "id": str(hostel.id),
        "name": hostel.name,
        "slug": hostel.slug,
        "description": hostel.description,
        "city": hostel.city,
        "state": hostel.state,
        "hostel_type": hostel.hostel_type,
        "status": hostel.status,
        "is_public": hostel.is_public,
        "is_featured": hostel.is_featured,
        "rating": round(avg_rating, 1),
        "total_reviews": review_count,
        "starting_price": starting_monthly_price,
        "starting_daily_price": starting_daily_price,
        "starting_monthly_price": starting_monthly_price,
        "available_beds": available_beds,
        "is_available": available_beds > 0,
        "availability_status": "available" if available_beds > 0 else "no_room_available",
        "created_at": hostel.created_at,
        "updated_at": hostel.updated_at,
    }


class HostelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = HostelRepository(session)
        self.room_repository = RoomRepository(session)

    async def _bulk_stats(self, hostel_ids: list[str]) -> dict[str, tuple[float, int, float, float]]:
        rating_result = await self.session.execute(
            select(
                Review.hostel_id,
                func.avg(Review.overall_rating).label("avg_rating"),
                func.count(Review.id).label("review_count"),
            )
            .where(
                Review.hostel_id.in_(hostel_ids),
                Review.is_published.is_(True),
            )
            .group_by(Review.hostel_id)
        )
        ratings: dict[str, tuple[float, int]] = {
            str(row.hostel_id): (float(row.avg_rating or 0), int(row.review_count or 0))
            for row in rating_result.all()
        }

        price_result = await self.session.execute(
            select(
                Room.hostel_id,
                func.min(Room.monthly_rent).label("min_price"),
                func.min(Room.daily_rent).label("min_daily_price"),
            )
            .where(Room.hostel_id.in_(hostel_ids), Room.is_active.is_(True))
            .group_by(Room.hostel_id)
        )
        prices: dict[str, tuple[float, float]] = {
            str(row.hostel_id): (float(row.min_price or 0), float(row.min_daily_price or 0))
            for row in price_result.all()
        }

        result: dict[str, tuple[float, int, float, float]] = {}
        for hid in hostel_ids:
            avg, count = ratings.get(hid, (0.0, 0))
            monthly_price, daily_price = prices.get(hid, (0.0, 0.0))
            result[hid] = (avg, count, monthly_price, daily_price)
        return result

    async def _bulk_available_beds(
        self,
        hostel_ids: list[str],
        start_date: date | datetime | None = None,
        end_date: date | datetime | None = None,
    ) -> dict[str, int]:
        start_date = start_date or date.today()
        end_date = end_date or (start_date + timedelta(days=1))
        result = await self.session.execute(
            select(Room.id, Room.hostel_id)
            .where(Room.hostel_id.in_(hostel_ids), Room.is_active.is_(True))
        )
        available_by_hostel: dict[str, int] = {hid: 0 for hid in hostel_ids}
        for room_id, hostel_id in result.all():
            available = await self.room_repository.get_available_bed_count(
                str(room_id),
                start_date,
                end_date,
            )
            hid = str(hostel_id)
            available_by_hostel[hid] = available_by_hostel.get(hid, 0) + int(available or 0)
        return available_by_hostel

    async def _get_amenity_names(self, hostel_id: str) -> list[str]:
        result = await self.session.execute(
            select(HostelAmenity.name).where(HostelAmenity.hostel_id == hostel_id)
        )
        return [row[0] for row in result.all()]

    async def _get_images(self, hostel_id: str) -> list[dict]:
        from app.models.hostel import HostelImage
        result = await self.session.execute(
            select(HostelImage)
            .where(HostelImage.hostel_id == hostel_id)
            .order_by(HostelImage.sort_order)
        )
        return [
            {
                "id": str(img.id),
                "url": img.url,
                "thumbnail_url": img.thumbnail_url,
                "caption": img.caption,
                "image_type": img.image_type,
                "sort_order": img.sort_order,
                "is_primary": img.is_primary,
            }
            for img in result.scalars().all()
        ]

    async def list_public_hostels(
        self,
        *,
        city: str | None = None,
        hostel_type: str | None = None,
        room_type: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        available_from: date | None = None,
        available_to: date | None = None,
        sort: str | None = None,
        is_featured: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List public hostels with filters - FIXED VERSION"""
        try:
            # First, get all active public hostels directly
            from sqlalchemy import select, func
            from app.models.hostel import Hostel, HostelStatus
            
            # Simple query to get hostels - no joins first
            from sqlalchemy.orm import selectinload
            query = select(Hostel).options(selectinload(Hostel.images)).where(
                Hostel.is_public == True,
                Hostel.status == HostelStatus.ACTIVE
            )
            
            if city:
                query = query.where(Hostel.city.ilike(f"%{city}%"))
            if hostel_type:
                try:
                    from app.models.hostel import HostelType
                    query = query.where(Hostel.hostel_type == HostelType(hostel_type.lower()))
                except ValueError:
                    pass
            if is_featured is not None:
                query = query.where(Hostel.is_featured == is_featured)
            
            # Get total count
            count_result = await self.session.execute(select(func.count()).select_from(query.subquery()))
            total = int(count_result.scalar() or 0)
            
            # Get paginated hostels
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            result = await self.session.execute(query)
            hostels = list(result.scalars().all())
            
            if not hostels:
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "per_page": page_size,
                }
            
            hostel_ids = [str(hostel.id) for hostel in hostels]
            stats = await self._bulk_stats(hostel_ids)
            range_start = available_from or date.today()
            range_end = available_to or (range_start + timedelta(days=1))
            availability = await self._bulk_available_beds(hostel_ids, range_start, range_end)

            items = []
            for hostel in hostels:
                hid = str(hostel.id)
                avg_rating, review_count, monthly_price, daily_price = stats.get(
                    hid, (0.0, 0, 0.0, 0.0)
                )
                items.append({
                    "id": hid,
                    "name": hostel.name,
                    "slug": hostel.slug,
                    "description": hostel.description[:200] if hostel.description else "",
                    "city": hostel.city,
                    "state": hostel.state,
                    "hostel_type": hostel.hostel_type.value if hasattr(hostel.hostel_type, "value") else str(hostel.hostel_type),
                    "status": hostel.status.value if hasattr(hostel.status, "value") else str(hostel.status),
                    "is_public": hostel.is_public,
                    "is_featured": hostel.is_featured,
                    "rating": round(avg_rating, 1),
                    "total_reviews": review_count,
                    "starting_price": monthly_price,
                    "starting_daily_price": daily_price,
                    "starting_monthly_price": monthly_price,
                    "available_beds": availability.get(hid, 0),
                    "is_available": availability.get(hid, 0) > 0,
                    "availability_status": (
                        "available" if availability.get(hid, 0) > 0 else "no_room_available"
                    ),
                    "images": [
                        {
                            "id": str(img.id),
                            "url": img.url,
                            "thumbnail_url": img.thumbnail_url,
                            "caption": img.caption,
                            "is_primary": img.is_primary,
                            "sort_order": img.sort_order,
                        }
                        for img in hostel.images
                    ],
                    "created_at": hostel.created_at,
                    "updated_at": hostel.updated_at,
                })
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "per_page": page_size,
            }
            
        except Exception as e:
            print(f"Error in list_public_hostels: {e}")
            import traceback
            traceback.print_exc()
            return {
                "items": [],
                "total": 0,
                "page": page,
                "per_page": page_size,
            }

    async def get_public_hostel(self, slug: str) -> dict | None:
        hostel = await self.repository.get_by_slug(slug)
        if hostel is None:
            return None

        hid = str(hostel.id)
        stats = await self._bulk_stats([hid])
        avg_rating, review_count, monthly_price, daily_price = stats.get(hid, (0.0, 0, 0.0, 0.0))
        available_beds = await self._bulk_available_beds([hid])
        amenities = await self._get_amenity_names(hid)
        images = await self._get_images(hid)

        base = _build_hostel_dict(
            hostel,
            avg_rating,
            review_count,
            monthly_price,
            daily_price,
            available_beds.get(hid, 0),
        )
        base.update({
            "address_line1": hostel.address_line1,
            "address_line2": hostel.address_line2,
            "country": hostel.country,
            "pincode": hostel.pincode,
            "latitude": hostel.latitude,
            "longitude": hostel.longitude,
            "phone": hostel.phone,
            "email": hostel.email,
            "website": hostel.website,
            "rules_and_regulations": hostel.rules_and_regulations,
            "amenities": amenities,
            "images": images,
        })
        return base

    async def list_hostel_reviews(self, hostel_id: str, *, page: int = 1, page_size: int = 20) -> list[dict]:
        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Review)
            .where(Review.hostel_id == hostel_id, Review.is_published.is_(True))
            .order_by(Review.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        reviews = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "hostel_id": str(r.hostel_id),
                "visitor_id": str(r.visitor_id),
                "booking_id": str(r.booking_id) if r.booking_id else None,
                "overall_rating": r.overall_rating,
                "cleanliness_rating": r.cleanliness_rating,
                "food_rating": r.food_rating,
                "security_rating": r.security_rating,
                "value_rating": r.value_rating,
                "title": r.title,
                "content": r.content,
                "is_verified": r.is_verified,
                "admin_reply": r.admin_reply,
                "created_at": r.created_at,
            }
            for r in reviews
        ]

    async def list_hostel_rooms(
        self,
        hostel_id: str,
        start_date: date | datetime | None = None,
        end_date: date | datetime | None = None,
    ) -> list[dict]:
        rooms = await self.room_repository.list_by_hostel(hostel_id)
        start_date = start_date or date.today()
        end_date = end_date or (start_date + timedelta(days=1))
        result = []
        for room in rooms:
            available = await self.room_repository.get_available_bed_count(
                str(room.id), start_date, end_date
            )
            d = {
                "id": str(room.id),
                "hostel_id": str(room.hostel_id),
                "room_number": room.room_number,
                "floor": room.floor,
                "room_type": room.room_type,
                "total_beds": room.total_beds,
                "hourly_rent": float(room.hourly_rent or 0),
                "daily_rent": float(room.daily_rent),
                "monthly_rent": float(room.monthly_rent),
                "security_deposit": float(room.security_deposit),
                "dimensions": room.dimensions,
                "is_active": room.is_active,
                "available_beds": available,
                "is_available": available > 0,
                "availability_status": "available" if available > 0 else "no_room_available",
                "created_at": room.created_at,
                "updated_at": room.updated_at,
            }
            result.append(d)
        return result
