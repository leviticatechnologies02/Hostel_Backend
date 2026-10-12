# app/services/notice_service.py
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import select, or_, func, desc, exists
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Set
from app.models.operations import Notice, NoticeRead
from app.models.student import Student
from app.models.hostel import Hostel
from app.repositories.notice_repository import NoticeRepository
from app.schemas.notice import NoticeCreateRequest, NoticeUpdateRequest



class NoticeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = NoticeRepository(session)

    # ==================== CREATE ====================
    
    async def create_admin_notice(
        self,
        *,
        actor_id: str,
        payload: NoticeCreateRequest,
    ) -> Notice:
        """Create a notice (admin can target specific hostel or platform-wide)"""
        # Validate hostel_id if provided
        if payload.hostel_id:
            hostel_result = await self.session.execute(
                select(Hostel).where(Hostel.id == payload.hostel_id)
            )
            if not hostel_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Hostel with id {payload.hostel_id} not found."
                )
        
        notice = Notice(
            hostel_id=payload.hostel_id,
            title=payload.title,
            content=payload.content,
            notice_type=payload.notice_type,
            priority=payload.priority,
            is_published=payload.is_published,
            publish_at=payload.publish_at,
            expires_at=payload.expires_at,
            created_by=actor_id,
        )
        self.session.add(notice)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    # ==================== READ ====================
    
    async def get_notice_by_id(self, notice_id: str) -> Optional[Notice]:
        """Get a single notice by ID"""
        result = await self.session.execute(
            select(Notice).where(Notice.id == notice_id)
        )
        return result.scalar_one_or_none()
        
    async def list_admin_notices(
        self,
        *,
        hostel_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        is_published: Optional[bool] = None,
        notice_type: Optional[str] = None,
    ) -> dict:
        """List notices with pagination and filters for admin"""
        query = select(Notice)
        
        if hostel_id:
            query = query.where(Notice.hostel_id == hostel_id)
        
        if is_published is not None:
            query = query.where(Notice.is_published == is_published)
        
        if notice_type:
            query = query.where(Notice.notice_type == notice_type)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = int(total_result.scalar() or 0)
        
        # Get paginated results
        query = query.order_by(desc(Notice.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.session.execute(query)
        notices = list(result.scalars().all())
        
        # Convert to dict
        items = []
        for notice in notices:
            items.append({
                "id": str(notice.id),
                "hostel_id": str(notice.hostel_id) if notice.hostel_id else None,
                "title": notice.title,
                "content": notice.content,
                "notice_type": notice.notice_type,
                "priority": notice.priority,
                "is_published": notice.is_published,
                "publish_at": notice.publish_at.isoformat() if notice.publish_at else None,  # ADD THIS
                "expires_at": notice.expires_at.isoformat() if notice.expires_at else None,  # ADD THIS
                "created_by": str(notice.created_by),
                "created_at": notice.created_at.isoformat(),
                "updated_at": notice.updated_at.isoformat(),
                "read_count": 0,
                "total_students": 0,
            })
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    
    async def list_student_notices(
        self,
        *,
        student_user_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """List notices for student (their hostel + platform-wide, only published)"""
        # Get student's hostel
        result = await self.session.execute(
            select(Student).where(Student.user_id == student_user_id)
        )
        student = result.scalar_one_or_none()
        
        if not student:
            return {
                "items": [],
                "total": 0,
                "unread_count": 0,
                "page": page,
                "per_page": per_page,
            }
        
        now = datetime.now(timezone.utc)
        
        query = select(Notice).where(
            or_(
                Notice.hostel_id == str(student.hostel_id),
                Notice.hostel_id.is_(None)
            ),
            Notice.is_published == True,
            or_(
                Notice.publish_at.is_(None),
                Notice.publish_at <= now
            ),
            or_(
                Notice.expires_at.is_(None),
                Notice.expires_at > now
            )
        )
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = int(total_result.scalar() or 0)

        unread_count = await self._count_visible_unread_notices(
            student_user_id=student_user_id,
            hostel_id=str(student.hostel_id),
            now=now,
        )
        
        # Get paginated results
        query = query.order_by(desc(Notice.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.session.execute(query)
        notices = list(result.scalars().all())
        
        # Get read status for each notice
        items = []
        for notice in notices:
            # Check if student has read this notice
            read_result = await self.session.execute(
                select(NoticeRead).where(
                    NoticeRead.notice_id == str(notice.id),
                    NoticeRead.user_id == student_user_id
                )
            )
            is_read = read_result.scalar_one_or_none() is not None
            
            items.append({
                "id": str(notice.id),
                "hostel_id": str(notice.hostel_id) if notice.hostel_id else None,
                "title": notice.title,
                "content": notice.content,
                "notice_type": notice.notice_type,
                "priority": notice.priority,
                "is_published": notice.is_published,
                "publish_at": notice.publish_at.isoformat() if notice.publish_at else None,
                "expires_at": notice.expires_at.isoformat() if notice.expires_at else None,
                "created_by": str(notice.created_by),
                "created_at": notice.created_at.isoformat(),
                "updated_at": notice.updated_at.isoformat(),
                "read_count": 0,
                "total_students": 0,
                "is_read": is_read,
            })
        
        return {
            "items": items,
            "total": total,
            "unread_count": unread_count,
            "page": page,
            "per_page": per_page,
        }

    async def get_student_unread_count(self, *, student_user_id: str) -> int:
        """Count active notices visible to a student that they have not read."""
        result = await self.session.execute(
            select(Student.hostel_id).where(Student.user_id == student_user_id)
        )
        hostel_id = result.scalar_one_or_none()
        if hostel_id is None:
            return 0

        return await self._count_visible_unread_notices(
            student_user_id=student_user_id,
            hostel_id=str(hostel_id),
            now=datetime.now(timezone.utc),
        )

    async def _count_visible_unread_notices(
        self,
        *,
        student_user_id: str,
        hostel_id: str,
        now: datetime,
    ) -> int:
        read_exists = exists().where(
            NoticeRead.notice_id == Notice.id,
            NoticeRead.user_id == student_user_id,
        )
        query = select(func.count(Notice.id)).where(
            or_(Notice.hostel_id == hostel_id, Notice.hostel_id.is_(None)),
            Notice.is_published.is_(True),
            or_(Notice.publish_at.is_(None), Notice.publish_at <= now),
            or_(Notice.expires_at.is_(None), Notice.expires_at > now),
            ~read_exists,
        )
        result = await self.session.execute(query)
        return int(result.scalar() or 0)


    # ==================== UPDATE ====================
    
    async def update_notice(
        self,
        *,
        notice_id: str,
        payload: NoticeUpdateRequest,
    ) -> Notice:
        """Update a notice"""
        notice = await self.get_notice_by_id(notice_id)
        
        if not notice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notice not found."
            )
        
        update_data = payload.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(notice, field, value)
        
        await self.session.commit()
        await self.session.refresh(notice)
        return notice
    
    async def toggle_publish_status(
        self,
        *,
        notice_id: str,
    ) -> Notice:
        """Toggle notice published status (publish/unpublish)"""
        notice = await self.get_notice_by_id(notice_id)
        
        if not notice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notice not found."
            )
        
        notice.is_published = not notice.is_published
        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    # ==================== DELETE ====================
    
    async def delete_notice(
        self,
        *,
        notice_id: str,
    ) -> None:
        """Delete a notice"""
        notice = await self.get_notice_by_id(notice_id)
        
        if not notice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notice not found."
            )
        
        # Delete associated read records
        await self.session.execute(
            select(NoticeRead).where(NoticeRead.notice_id == notice_id)
        )
        
        await self.session.delete(notice)
        await self.session.commit()

    # ==================== READ TRACKING ====================
    
    async def mark_notice_as_read(
        self,
        *,
        notice_id: str,
        user_id: str,
    ) -> dict:
        """Mark a notice as read by a user"""
        # Check if notice exists and is published
        notice = await self.get_notice_by_id(notice_id)
        
        if not notice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notice not found."
            )
        
        # Check if already marked as read
        result = await self.session.execute(
            select(NoticeRead).where(
                NoticeRead.notice_id == notice_id,
                NoticeRead.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing is None:
            notice_read = NoticeRead(
                notice_id=notice_id,
                user_id=user_id,
            )
            self.session.add(notice_read)
            await self.session.commit()

        unread_count = await self.get_student_unread_count(
            student_user_id=user_id
        )
        return {
            "notice_id": notice_id,
            "is_read": True,
            "unread_count": unread_count,
        }
    
    async def get_user_read_notices(
        self,
        *,
        user_id: str,
    ) -> list[str]:
        """Get list of notice IDs that a user has read"""
        result = await self.session.execute(
            select(NoticeRead.notice_id).where(NoticeRead.user_id == user_id)
        )
        return [str(notice_id) for notice_id in result.scalars().all()]

    async def list_supervisor_notices(
        self,
        *,
        supervisor_id: str,
        page: int = 1,
        per_page: int = 20,
        is_published: Optional[bool] = None,
    ) -> dict:
        """List notices for supervisor (their assigned hostel + platform-wide)"""
        # Get supervisor's hostel IDs from the mapping table
        from app.models.hostel import SupervisorHostelMapping
        
        result = await self.session.execute(
            select(SupervisorHostelMapping.hostel_id).where(
                SupervisorHostelMapping.supervisor_id == supervisor_id
            )
        )
        hostel_ids = [str(hid) for hid in result.scalars().all()]
        
        if not hostel_ids:
            return {"items": [], "total": 0, "page": page, "per_page": per_page}
        
        # Build query
        from app.models.operations import Notice
        query = select(Notice).where(
            or_(
                Notice.hostel_id.in_(hostel_ids),
                Notice.hostel_id.is_(None)
            )
        )
        
        if is_published is not None:
            query = query.where(Notice.is_published == is_published)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = int(total_result.scalar() or 0)
        
        # Get paginated results
        query = query.order_by(desc(Notice.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.session.execute(query)
        notices = list(result.scalars().all())
        
        # Convert to dict - FIX: serialize datetime fields
        items = []
        for notice in notices:
            items.append({
                "id": str(notice.id),
                "hostel_id": str(notice.hostel_id) if notice.hostel_id else None,
                "title": notice.title,
                "content": notice.content,
                "notice_type": notice.notice_type,
                "priority": notice.priority,
                "is_published": notice.is_published,
                "publish_at": notice.publish_at.isoformat() if notice.publish_at else None,
                "expires_at": notice.expires_at.isoformat() if notice.expires_at else None,
                "created_by": str(notice.created_by),
                "created_at": notice.created_at.isoformat(),
                "updated_at": notice.updated_at.isoformat(),
                "read_count": 0,
                "total_students": 0,
            })
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }    
    async def create_supervisor_notice(
        self,
        *,
        actor_id: str,
        payload: NoticeCreateRequest,
    ) -> Notice:
        """Create a notice (supervisor can only create for their assigned hostel)"""
        # Get supervisor's hostel IDs
        from app.models.hostel import SupervisorHostelMapping
        result = await self.session.execute(
            select(SupervisorHostelMapping.hostel_id).where(
                SupervisorHostelMapping.supervisor_id == actor_id
            )
        )
        hostel_ids = [str(hid) for hid in result.scalars().all()]
        
        if not hostel_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No hostel assigned to you."
            )
        
        # Supervisor can only create notices for their assigned hostel
        target_hostel_id = payload.hostel_id if payload.hostel_id else hostel_ids[0]
        
        if target_hostel_id not in hostel_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only create notices for your assigned hostel."
            )
        
        notice = Notice(
            hostel_id=target_hostel_id,
            title=payload.title,
            content=payload.content,
            notice_type=payload.notice_type,
            priority=payload.priority,
            is_published=payload.is_published,
            publish_at=payload.publish_at,
            expires_at=payload.expires_at,
            created_by=actor_id,
        )
        self.session.add(notice)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(notice)
        return notice
    

    async def list_notice_read_stats(self, *, hostel_id: str) -> list[dict]:        
        # Get total students in this hostel
        total_result = await self.session.execute(
            select(func.count(Student.id)).where(Student.hostel_id == hostel_id)
        )
        total_students = int(total_result.scalar() or 0)
        
        # Get all notices for this hostel (including platform-wide)
        result = await self.session.execute(
            select(Notice).where(
                or_(
                    Notice.hostel_id == hostel_id,
                    Notice.hostel_id.is_(None)
                )
            ).order_by(Notice.created_at.desc())
        )
        notices = list(result.scalars().all())
        
        out: list[dict] = []
        for notice in notices:
            # Count how many students have read this notice
            read_result = await self.session.execute(
                select(func.count(NoticeRead.id))
                .join(Student, Student.user_id == NoticeRead.user_id)
                .where(
                    NoticeRead.notice_id == str(notice.id),
                    Student.hostel_id == hostel_id,
                )
            )
            read_count = int(read_result.scalar() or 0)
            
            out.append({
                "notice_id": str(notice.id),
                "notice_title": notice.title,
                "read_count": read_count,
                "total_students": total_students,
                "read_percentage": round((read_count / total_students * 100) if total_students > 0 else 0, 1)
            })
        
        return out
