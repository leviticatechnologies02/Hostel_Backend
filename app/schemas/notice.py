# app/schemas/notice.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_serializer
from app.schemas.base import APIModel


class NoticeCreateRequest(BaseModel):
    """Request to create a new notice"""
    hostel_id: Optional[str] = Field(default=None, description="If None, notice is platform-wide")
    title: str = Field(min_length=3, max_length=255)
    content: str = Field(min_length=5)
    notice_type: str = Field(min_length=2, max_length=100, description="general, maintenance, event, policy, safety, payment")
    priority: str = Field(min_length=2, max_length=50, description="low, medium, high")
    is_published: bool = Field(default=True)
    publish_at: Optional[datetime] = Field(default=None, description="Schedule for future publishing")
    expires_at: Optional[datetime] = Field(default=None, description="Auto-expire after this date")


class NoticeUpdateRequest(BaseModel):
    """Request to update an existing notice"""
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    content: Optional[str] = Field(default=None, min_length=5)
    notice_type: Optional[str] = Field(default=None, min_length=2, max_length=100)
    priority: Optional[str] = Field(default=None, min_length=2, max_length=50)
    is_published: Optional[bool] = None
    publish_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class NoticeResponse(APIModel):
    """Notice response model"""
    id: str
    hostel_id: Optional[str] = None
    title: str
    content: str
    notice_type: str
    priority: str
    is_published: bool
    publish_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    read_count: int = 0
    total_students: int = 0
    is_read: bool = False
    
    @field_serializer('created_at', 'updated_at', 'publish_at', 'expires_at')
    def serialize_datetime(self, dt: datetime, _info):
        if dt is None:
            return None
        return dt.isoformat()

class NoticeReadStatsItem(APIModel):
    """Per-notice read counts"""
    notice_id: str
    read_count: int
    total_students: int


class NoticeListResponse(BaseModel):
    """Paginated notice list response"""
    items: list[NoticeResponse]
    total: int
    unread_count: int = 0
    page: int
    per_page: int


class NoticeUnreadCountResponse(BaseModel):
    """Unread notice count used by the student navigation badge."""
    unread_count: int
