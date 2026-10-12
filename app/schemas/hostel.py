from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.base import TimestampedResponse


class HostelListItem(TimestampedResponse):
    id: str
    name: str
    slug: str
    description: str
    city: str
    state: str
    hostel_type: str
    status: str
    is_public: bool
    is_featured: bool
    is_active: bool = False
    is_verified: bool = False
    status_reason: Optional[str] = None
    rating: float = 0.0
    total_reviews: int = 0
    starting_price: float = 0.0
    starting_daily_price: float = 0.0
    starting_monthly_price: float = 0.0
    available_beds: int = 0
    is_available: bool = False
    availability_status: str = "no_room_available"
    images: list[dict] = []          # ← primary + gallery images for card display


class HostelDetailResponse(HostelListItem):
    address_line1: str
    address_line2: Optional[str] = None
    country: str
    pincode: str
    latitude: float
    longitude: float
    phone: str
    email: str
    website: Optional[str] = None
    document_url: Optional[str] = None
    document_type: Optional[str] = None
    rules_and_regulations: Optional[str] = None
    amenities: list[str] = []
    images: list[dict] = []


class PaginatedHostelListResponse(BaseModel):
    items: list[HostelListItem]
    total: int
    page: int
    per_page: int


class PublicCityResponse(BaseModel):
    city: str
    hostel_count: int


class HostelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, min_length=10)
    address_line1: str | None = Field(default=None, min_length=2, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=120)
    pincode: str | None = Field(default=None, min_length=3, max_length=20)
    phone: str | None = Field(default=None, min_length=5, max_length=30)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    is_featured: bool | None = None
    is_public: bool | None = None
    rules_and_regulations: str | None = None


class InquiryRequest(BaseModel):
    hostel_id: str
    name: str
    email: str
    phone: str
    message: str


from typing import Optional, Any
from pydantic import BaseModel, Field, EmailStr, BeforeValidator
from datetime import datetime, date
from typing_extensions import Annotated
from app.models.hostel import HostelType

def lowercase_str(v: Any) -> Any:
    if isinstance(v, str):
        return v.lower()
    return v

class HostelRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=10)
    hostel_type: Annotated[HostelType, BeforeValidator(lowercase_str)]
    address_line1: str = Field(..., min_length=2, max_length=255)
    address_line2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(..., min_length=2, max_length=120)
    state: str = Field(..., min_length=2, max_length=120)
    country: str = Field(default="India", min_length=2, max_length=120)
    pincode: str = Field(..., min_length=3, max_length=20)
    latitude: float
    longitude: float
    phone: str = Field(..., min_length=5, max_length=30)
    email: str = Field(..., min_length=5, max_length=255)
    website: Optional[str] = Field(default=None, max_length=255)
    rules_and_regulations: Optional[str] = None
    document_url: Optional[str] = Field(default=None, max_length=500)
    document_type: Optional[str] = Field(default=None, max_length=100)

