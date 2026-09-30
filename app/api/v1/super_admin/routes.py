from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Request

from fastapi.responses import Response

from datetime import date, timedelta 

import re
from app.core.security import verify_password, hash_password
from app.repositories.user_repository import UserRepository
from sqlalchemy import select

from app.api.v1.supervisor.routes import SupervisorUser

from app.models.user import User, UserRole

from uuid import uuid4

from datetime import UTC, datetime

from app.dependencies import CurrentUser, require_roles

from app.dependencies import DBSession

from app.models.hostel import HostelStatus

from app.schemas.maintenance import MaintenanceResponse, MaintenanceUpdateRequest

from app.schemas.super_admin import (

    AssignHostelRequest,

    SuperAdminProfileResponse,

    SuperAdminProfileUpdateRequest,

    ValidatePasswordRequest,

    PasswordValidationResponse,

    AssignHostelsRequest,

    ChangePasswordRequest,

    SuperAdminHostelListResponse,

    SuperAdminHostelRejectRequest,
    SuperAdminHostelApproveRequest,
    SuperAdminHostelRequestChangesRequest,

    SuperAdminAdminCreateRequest,

    SuperAdminAdminResponse,

    SuperAdminDashboardResponse,

    SuperAdminHostelCreateRequest,

    SuperAdminHostelResponse,

    SuperAdminSubscriptionResponse,

    SuperAdminSubscriptionCreateRequest,

    SuperAdminSubscriptionUpdateRequest,

    SuperAdminSubscriptionDetailResponse,

)

from app.services.super_admin_service import SuperAdminService

from app.schemas.student import CompleteStudentDetailResponse

from fastapi.exceptions import RequestValidationError

from fastapi.responses import JSONResponse





router = APIRouter()

SuperAdmin = Annotated[CurrentUser, Depends(require_roles("super_admin"))]





def validate_email(email: str) -> bool:

    """

    Validate email format and domain.

    

    Checks:

    - Valid email format (contains @ and .)

    - Domain has at least one dot after @

    - No spaces

    """

    email = email.strip()

    

    # Check for empty

    if not email:

        return False

    

    # Check for spaces

    if ' ' in email:

        return False

    

    # Check for @ symbol

    if '@' not in email:

        return False

    

    # Split into local and domain parts

    local_part, domain_part = email.rsplit('@', 1)

    

    # Check local part is not empty

    if not local_part:

        return False

    

    # Check domain has at least one dot and not empty

    if not domain_part or '.' not in domain_part:

        return False

    

    # Check domain doesn't start or end with dot

    if domain_part.startswith('.') or domain_part.endswith('.'):

        return False

    

    # Check for valid characters (basic check)

    # Allow letters, numbers, dots, hyphens, underscores in local part

    valid_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    return bool(re.match(valid_pattern, email))





@router.get("/dashboard", response_model=SuperAdminDashboardResponse)
async def dashboard(current_user: SuperAdmin, db: DBSession):
    """**Platform overview** — total hostels, admins, and active subscriptions."""
    data = await SuperAdminService(db).get_dashboard()
    
    # Fetch super admin's full name
    from sqlalchemy import select
    from app.models.user import User
    user_result = await db.execute(select(User.full_name).where(User.id == current_user.id))
    admin_name = user_result.scalar_one_or_none() or "Super Admin"
    
    data.super_admin_name = admin_name
    return data






@router.get("/hostels", response_model=list[SuperAdminHostelResponse])

async def list_hostels(_: SuperAdmin, db: DBSession, status: str | None = None, unassigned_only: bool = False, exclude_suspended_rejected: bool = False):

    """**List all hostels** across the platform in all statuses. Pass unassigned_only=true to get only hostels without an admin. Pass exclude_suspended_rejected=true to filter out rejected/suspended hostels."""

    return await SuperAdminService(db).list_hostels(status=status, unassigned_only=unassigned_only, exclude_suspended_rejected=exclude_suspended_rejected)





@router.get("/hostels/paginated", response_model=SuperAdminHostelListResponse)

async def list_hostels_paginated(

    _: SuperAdmin,

    db: DBSession,

    status: str | None = None,

    page: int = 1,

    per_page: int = 20,

):

    """Spec-compatible paginated hostel list with optional status filter."""

    return await SuperAdminService(db).list_hostels_paginated(status=status, page=page, per_page=per_page)





@router.get("/hostels/{hostel_id}", response_model=SuperAdminHostelResponse)

async def get_hostel(hostel_id: str, _: SuperAdmin, db: DBSession):

    return await SuperAdminService(db).get_hostel(hostel_id)





@router.post("/hostels", response_model=SuperAdminHostelResponse, status_code=201)

async def create_hostel(payload: SuperAdminHostelCreateRequest, _: SuperAdmin, db: DBSession):

    """**Create a new hostel.** Created in `pending_approval` status by default."""

    return await SuperAdminService(db).create_hostel(payload)








@router.post("/hostels/{hostel_id}/approve", response_model=SuperAdminHostelResponse)
async def approve_hostel(hostel_id: str, current_user: SuperAdmin, db: DBSession, payload: SuperAdminHostelApproveRequest | None = None):
    """**Approve a hostel** — sets status to `active`, making it publicly visible, and emails the owner."""
    note = payload.note if payload else None
    return await SuperAdminService(db).approve_hostel(hostel_id=hostel_id, approved_by=current_user.id, note=note)


@router.post("/hostels/{hostel_id}/reject", response_model=SuperAdminHostelResponse)
async def reject_hostel(hostel_id: str, payload: SuperAdminHostelRejectRequest, current_user: SuperAdmin, db: DBSession):
    """**Reject a hostel** — sets status to `rejected`. Hostel will not appear publicly, and owner is notified."""
    return await SuperAdminService(db).reject_hostel(hostel_id=hostel_id, rejected_by=current_user.id, reason=payload.reason)


@router.post("/hostels/{hostel_id}/request-changes", response_model=SuperAdminHostelResponse)
async def request_hostel_changes(hostel_id: str, payload: SuperAdminHostelRequestChangesRequest, current_user: SuperAdmin, db: DBSession):
    """**Request changes** — sets status to `changes_requested`. Owner is notified."""
    return await SuperAdminService(db).request_hostel_changes(hostel_id=hostel_id, requested_by=current_user.id, reason=payload.reason)


@router.post("/hostels/{hostel_id}/suspend", response_model=SuperAdminHostelResponse)
async def suspend_hostel(hostel_id: str, _: SuperAdmin, db: DBSession):
    """**Suspend a hostel** — temporarily removes it from public listing."""
    return await SuperAdminService(db).update_hostel_status(hostel_id, HostelStatus.SUSPENDED)


@router.delete("/hostels/{hostel_id}", status_code=200)
async def delete_hostel(hostel_id: str, _: SuperAdmin, db: DBSession):
    """**Permanently delete a hostel** and all its associated data (images, rooms, bookings, mappings).
    
    ⚠️ This action is **irreversible**. Use with caution.
    Only super admins can perform this action.
    """
    return await SuperAdminService(db).delete_hostel(hostel_id)





@router.get("/admins", response_model=list[SuperAdminAdminResponse])

async def list_admins(_: SuperAdmin, db: DBSession):

    """**List all hostel admins** on the platform."""

    return await SuperAdminService(db).list_admins()



@router.post("/admins", response_model=SuperAdminAdminResponse)
async def create_admin(payload: SuperAdminAdminCreateRequest, _: SuperAdmin, db: DBSession):
    """**Create a new hostel admin**."""
    return await SuperAdminService(db).create_admin(payload)

@router.delete("/admins/{admin_id}", status_code=200)
async def delete_admin(admin_id: str, _: SuperAdmin, db: DBSession):
    """**Delete a hostel admin** and all associated mappings."""
    return await SuperAdminService(db).delete_admin(admin_id)





@router.post("/admins/{admin_id}/assign-hostels")

async def assign_hostels(

    admin_id: str, 

    payload: AssignHostelsRequest, 

    current_user: SuperAdmin, 

    db: DBSession

):

    """

    **Assign hostels to an admin.**



    Replaces existing assignments. Pass an array of `hostel_ids`.

    The admin will only be able to manage the assigned hostels.

    """

    from app.models.hostel import AdminHostelMapping, Hostel

    from sqlalchemy import select, delete

    

    # Verify admin exists

    result = await db.execute(

        select(User).where(User.id == admin_id, User.role == UserRole.HOSTEL_ADMIN)

    )

    admin_user = result.scalar_one_or_none()

    

    if admin_user is None:

        raise HTTPException(status_code=404, detail="Admin not found.")

    

    # Delete existing assignments

    await db.execute(

        delete(AdminHostelMapping).where(AdminHostelMapping.admin_id == admin_id)

    )

    

    # Create new assignments

    for index, hostel_id in enumerate(payload.hostel_ids):

        # Verify hostel exists

        hostel_result = await db.execute(select(Hostel).where(Hostel.id == hostel_id))

        if hostel_result.scalar_one_or_none() is None:

            raise HTTPException(status_code=404, detail=f"Hostel {hostel_id} not found.")

        

        mapping = AdminHostelMapping(

            id=uuid4(),

            admin_id=admin_id,

            hostel_id=hostel_id,

            is_primary=(index == 0),

            assigned_by=current_user.id,

            assigned_at=datetime.now(UTC)

        )

        db.add(mapping)

    

    await db.commit()

    return {"admin_id": admin_id, "hostel_ids": payload.hostel_ids}



@router.post("/admins/{admin_id}/assign-hostel")

async def assign_hostel(admin_id: str, payload: AssignHostelRequest, current_user: SuperAdmin, db: DBSession):

    return await SuperAdminService(db).assign_hostel(

        actor_id=current_user.id,

        admin_id=admin_id,

        payload=payload,

    )


@router.delete("/admins/{admin_id}/hostels/{hostel_id}")
async def unassign_hostel(admin_id: str, hostel_id: str, current_user: SuperAdmin, db: DBSession):
    """Unassign a hostel from an admin, making it available again."""
    return await SuperAdminService(db).unassign_hostel(
        actor_id=current_user.id,
        admin_id=admin_id,
        hostel_id=hostel_id,
    )





# ==================== SUBSCRIPTION ENDPOINTS ====================





@router.get("/subscriptions/stats")
async def get_subscription_stats(
    _: SuperAdmin,
    db: DBSession,
):
    """
    Get subscription statistics for dashboard.
    """
    from sqlalchemy import text
    
    try:
        # Get total subscriptions
        result = await db.execute(text("SELECT COUNT(*) FROM subscriptions"))
        total = result.scalar() or 0
        
        # Get active subscriptions
        result = await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'"))
        active = result.scalar() or 0
        
        # Get expired
        result = await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE status = 'expired'"))
        expired = result.scalar() or 0
        
        # Get cancelled
        result = await db.execute(text("SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled'"))
        cancelled = result.scalar() or 0
        
        # Get revenue
        result = await db.execute(text("SELECT COALESCE(SUM(price_monthly), 0) FROM subscriptions WHERE status = 'active'"))
        revenue = float(result.scalar() or 0)
        
        # Get tier distribution
        result = await db.execute(text("SELECT tier, COUNT(*) FROM subscriptions WHERE status = 'active' GROUP BY tier"))
        tier_dist = {}
        for row in result:
            tier_dist[row[0]] = row[1]
        
        return {
            "total_subscriptions": total,
            "active_subscriptions": active,
            "expired_subscriptions": expired,
            "cancelled_subscriptions": cancelled,
            "expiring_soon": 0,
            "monthly_recurring_revenue": revenue,
            "tier_distribution": tier_dist,
        }
    except Exception as e:
        return {
            "total_subscriptions": 0,
            "active_subscriptions": 0,
            "expired_subscriptions": 0,
            "cancelled_subscriptions": 0,
            "expiring_soon": 0,
            "monthly_recurring_revenue": 0.0,
            "tier_distribution": {},
        }


@router.get("/subscriptions", response_model=list[SuperAdminSubscriptionDetailResponse])
async def list_subscriptions(
    _: SuperAdmin,
    db: DBSession,
    status_filter: str | None = Query(None, description="Filter by status: active, expired, cancelled"),
    hostel_id: str | None = Query(None, description="Filter by hostel ID"),
):
    """List all hostel subscriptions with optional filtering."""
    from sqlalchemy import select
    from app.models.operations import Subscription
    from app.models.hostel import Hostel
    
    query = select(Subscription)
    
    if status_filter:
        query = query.where(Subscription.status == status_filter)
    
    if hostel_id:
        query = query.where(Subscription.hostel_id == hostel_id)
    
    query = query.order_by(Subscription.created_at.desc())
    
    result = await db.execute(query)
    subscriptions = list(result.scalars().all())
    
    # Build response manually
    response = []
    for sub in subscriptions:
        # Get hostel name
        hostel_result = await db.execute(
            select(Hostel.name).where(Hostel.id == sub.hostel_id)
        )
        hostel_name = hostel_result.scalar_one_or_none()
        
        response.append({
            "id": str(sub.id),
            "hostel_id": str(sub.hostel_id),
            "hostel_name": hostel_name,
            "tier": sub.tier,
            "price_monthly": float(sub.price_monthly),
            "start_date": sub.start_date.isoformat(),
            "end_date": sub.end_date.isoformat(),
            "status": sub.status,
            "auto_renew": sub.auto_renew,
            "created_at": sub.created_at,
            "updated_at": sub.updated_at,
        })
    
    return response

@router.get("/subscriptions/{subscription_id}", response_model=SuperAdminSubscriptionDetailResponse)
async def get_subscription(
    subscription_id: str,
    _: SuperAdmin,
    db: DBSession,
):
    """Get a single subscription by ID."""
    from sqlalchemy import select
    from app.models.operations import Subscription
    from app.models.hostel import Hostel
    from datetime import date
    
    try:
        # Validate UUID format
        import uuid
        try:
            uuid.UUID(subscription_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invalid subscription ID format"
            )
        
        result = await db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription with id '{subscription_id}' not found."
            )
        
        hostel_result = await db.execute(
            select(Hostel).where(Hostel.id == subscription.hostel_id)
        )
        hostel = hostel_result.scalar_one_or_none()
        
        days_remaining = None
        if subscription.status == "active" and subscription.end_date:
            days_remaining = (subscription.end_date - date.today()).days
            days_remaining = max(0, days_remaining)
        
        return {
            "id": str(subscription.id),
            "hostel_id": str(subscription.hostel_id),
            "hostel_name": hostel.name if hostel else None,
            "tier": subscription.tier,
            "price_monthly": float(subscription.price_monthly),
            "start_date": subscription.start_date.isoformat(),
            "end_date": subscription.end_date.isoformat(),
            "status": subscription.status,
            "auto_renew": subscription.auto_renew,
            "days_remaining": days_remaining,
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription not found"
        )
@router.post("/subscriptions", status_code=201)
async def create_subscription(
    request: Request,
    _: SuperAdmin,
    db: DBSession,
):
    """Create a new subscription for a hostel."""
    from sqlalchemy import select
    from app.models.operations import Subscription
    from app.models.hostel import Hostel
    from datetime import date
    
    # Parse body manually to avoid validation issues
    body = await request.json()
    
    hostel_id = body.get("hostel_id")
    tier = body.get("tier")
    price_monthly = body.get("price_monthly")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    auto_renew = body.get("auto_renew", True)
    status = body.get("status", "active")
    
    # Validate required fields
    if not hostel_id:
        raise HTTPException(status_code=400, detail="hostel_id is required")
    if not tier:
        raise HTTPException(status_code=400, detail="tier is required")
    if price_monthly is None:
        raise HTTPException(status_code=400, detail="price_monthly is required")
    
    # Parse dates
    try:
        start_date = date.fromisoformat(start_date) if start_date else date.today()
        end_date = date.fromisoformat(end_date) if end_date else date.today()
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Check if hostel exists
    hostel_result = await db.execute(
        select(Hostel).where(Hostel.id == hostel_id)
    )
    hostel = hostel_result.scalar_one_or_none()
    if not hostel:
        raise HTTPException(
            status_code=404,
            detail=f"Hostel with id '{hostel_id}' not found."
        )
    
    # Check for existing active subscription
    existing = await db.execute(
        select(Subscription).where(
            Subscription.hostel_id == hostel_id,
            Subscription.status == "active"
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Hostel already has an active subscription. Please cancel it first."
        )
    
    # Create subscription
    subscription = Subscription(
        hostel_id=hostel_id,
        tier=tier,
        price_monthly=float(price_monthly),
        start_date=start_date,
        end_date=end_date,
        status=status,
        auto_renew=auto_renew,
    )
    
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    
    return {
        "id": str(subscription.id),
        "hostel_id": str(subscription.hostel_id),
        "hostel_name": hostel.name,
        "tier": subscription.tier,
        "price_monthly": float(subscription.price_monthly),
        "start_date": subscription.start_date.isoformat(),
        "end_date": subscription.end_date.isoformat(),
        "status": subscription.status,
        "auto_renew": subscription.auto_renew,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }

@router.patch("/subscriptions/{subscription_id}", response_model=SuperAdminSubscriptionDetailResponse)
async def update_subscription(
    subscription_id: str,
    payload: SuperAdminSubscriptionUpdateRequest,
    _: SuperAdmin,
    db: DBSession,
):
    """Update an existing subscription."""
    from app.models.hostel import Hostel
    from app.models.operations import Subscription
    from datetime import date
    
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription with id '{subscription_id}' not found."
        )
    
    update_data = payload.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if value is not None:
            setattr(subscription, field, value)
    
    await db.commit()
    await db.refresh(subscription)
    
    hostel_result = await db.execute(
        select(Hostel).where(Hostel.id == subscription.hostel_id)
    )
    hostel = hostel_result.scalar_one_or_none()
    
    days_remaining = None
    if subscription.status == "active" and subscription.end_date:
        days_remaining = (subscription.end_date - date.today()).days
        days_remaining = max(0, days_remaining)
    
    return {
        "id": str(subscription.id),
        "hostel_id": str(subscription.hostel_id),
        "hostel_name": hostel.name if hostel else None,
        "tier": subscription.tier,
        "price_monthly": float(subscription.price_monthly),
        "start_date": subscription.start_date.isoformat(),
        "end_date": subscription.end_date.isoformat(),
        "status": subscription.status,
        "auto_renew": subscription.auto_renew,
        "days_remaining": days_remaining,
        "created_at": subscription.created_at,
        "updated_at": subscription.updated_at,
    }

@router.post("/subscriptions/{subscription_id}/cancel", response_model=dict)
async def cancel_subscription(
    subscription_id: str,
    _: SuperAdmin,
    db: DBSession,
):
    """Cancel an active subscription."""
    from sqlalchemy import select
    from app.models.operations import Subscription
    
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription not found"
        )
    
    if subscription.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel subscription with status '{subscription.status}'"
        )
    
    subscription.status = "cancelled"
    subscription.auto_renew = False
    
    await db.commit()
    await db.refresh(subscription)
    
    return {
        "id": str(subscription.id),
        "status": subscription.status,
        "auto_renew": subscription.auto_renew,
        "message": "Subscription cancelled successfully"
    }

@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(
    subscription_id: str,
    _: SuperAdmin,
    db: DBSession,
):
    """Delete a subscription (hard delete)."""
    from sqlalchemy import select
    from app.models.operations import Subscription
    
    result = await db.execute(
        select(Subscription).where(Subscription.id == subscription_id)
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription not found"
        )
    
    if subscription.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete active subscription. Cancel it first."
        )
    
    await db.delete(subscription)
    await db.commit()
    
    return Response(status_code=204)

@router.get("/profile", response_model=SuperAdminProfileResponse)
async def get_super_admin_profile(
    current_user: SuperAdmin,
    db: DBSession,
):
    """
    **Get super admin profile information.**
    
    Returns personal details including name, email, phone.
    """
    from app.models.user import User
    from sqlalchemy import select
    
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "profile_picture_url": user.profile_picture_url,
        "is_email_verified": user.is_email_verified,
        "is_phone_verified": user.is_phone_verified,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }

@router.patch("/profile", response_model=SuperAdminProfileResponse)
async def update_super_admin_profile(
    payload: SuperAdminProfileUpdateRequest,
    current_user: SuperAdmin,
    db: DBSession,
):
    """
    **Update super admin profile.**
    
    Can update: full_name, phone, profile_picture_url.
    """
    from app.models.user import User
    from sqlalchemy import select
    
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Update full name
    if payload.full_name is not None:
        user.full_name = payload.full_name
    
    # Update phone (check uniqueness)
    if payload.phone is not None:
        # Validate phone format
        import re
        digits_only = re.sub(r'[^0-9]', '', payload.phone)
        
        if len(digits_only) < 10 or len(digits_only) > 13:
            raise HTTPException(
                status_code=400,
                detail="Phone number must have between 10 and 13 digits."
            )
        
        # Check if phone already taken by another user
        existing = await db.execute(
            select(User).where(
                User.phone == payload.phone,
                User.id != current_user.id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Phone number already registered by another user."
            )
        user.phone = payload.phone
    
    # Update profile picture

    
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "profile_picture_url": user.profile_picture_url,
        "is_email_verified": user.is_email_verified,
        "is_phone_verified": user.is_phone_verified,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.post("/change-password")
async def change_super_admin_password(
    payload: ChangePasswordRequest,
    current_user: SuperAdmin,
    db: DBSession
):
    """
    **Change super admin password.**
    
    Requirements:
    - Current password must be correct
    - New password: min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char
    - New password and confirm password must match
    
    After successful change, all other sessions are revoked for security.
    """
    from app.models.user import User
    from sqlalchemy import select
    from datetime import UTC, datetime
    
    # Validate passwords match
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match."
        )
    
    # Get the user record
    result = await db.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    # Verify current password
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Current password is incorrect."
        )
    
    # Validate new password strength
    errors = []
    if len(payload.new_password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r'[A-Z]', payload.new_password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', payload.new_password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', payload.new_password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', payload.new_password):
        errors.append("Password must contain at least one special character")
    
    if errors:
        raise HTTPException(
            status_code=400,
            detail="; ".join(errors)
        )
    
    # Hash and update password
    user.password_hash = hash_password(payload.new_password)
    
    # Revoke all other sessions for security
    repo = UserRepository(db)
    await repo.revoke_all_refresh_tokens(
        user_id=current_user.id,
        revoked_at=datetime.now(UTC)
    )
    
    await db.commit()
    
    return {
        "message": "Password changed successfully.",
        "user_id": str(user.id)
    }

@router.post("/validate-password", response_model=PasswordValidationResponse)
async def validate_password(payload: ValidatePasswordRequest):
    """
    Validate password strength without changing it.
    Returns 200 even for invalid passwords (with errors list).
    """
    errors = []
    
    if len(payload.password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r'[A-Z]', payload.password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', payload.password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', payload.password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', payload.password):
        errors.append("Password must contain at least one special character")
    
    # Always return 200, even for invalid passwords
    return PasswordValidationResponse(
        is_valid=len(errors) == 0,
        errors=errors
    )


# ==================== PAYMENT DETAIL APIs (Super Admin & Hostel Admin) ====================

@router.get("/payments", tags=["Payments"])
async def list_all_payments(
    _: SuperAdmin,
    db: DBSession,
    hostel_id: str | None = None,
    booking_id: str | None = None,
    visitor_id: str | None = None,
    payment_status: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    **[Super Admin] List all payments across the platform.**

    Supports filtering by hostel, booking, visitor, and payment status.
    Returns full payment details: amount, transaction ID, method, date/time, visitor info.
    """
    from sqlalchemy import func
    from app.models.payment import Payment
    from app.models.booking import Booking
    from app.models.user import User
    from app.models.hostel import Hostel

    query = select(Payment)
    count_query = select(func.count()).select_from(Payment)

    if hostel_id:
        query = query.where(Payment.hostel_id == hostel_id)
        count_query = count_query.where(Payment.hostel_id == hostel_id)
    if booking_id:
        query = query.where(Payment.booking_id == booking_id)
        count_query = count_query.where(Payment.booking_id == booking_id)
    if payment_status:
        query = query.where(Payment.status == payment_status)
        count_query = count_query.where(Payment.status == payment_status)

    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    query = query.order_by(Payment.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    payments = result.scalars().all()

    # Batch-load hostel names for all payments
    hostel_ids = list({str(p.hostel_id) for p in payments if p.hostel_id})
    hostel_name_map = {}
    if hostel_ids:
        hostel_result = await db.execute(
            select(Hostel.id, Hostel.name).where(Hostel.id.in_(hostel_ids))
        )
        for hostel_id_val, hostel_name_val in hostel_result.all():
            hostel_name_map[str(hostel_id_val)] = hostel_name_val

    items = []
    for p in payments:
        # Get visitor/user info from booking
        visitor_info = None
        payer_name = None

        if p.booking_id:
            from app.models.student import Student
            booking_result = await db.execute(
                select(Booking, User)
                .join(User, User.id == Booking.visitor_id)
                .where(Booking.id == p.booking_id)
            )
            row = booking_result.first()
            if row:
                booking, user = row
                payer_name = booking.full_name or user.full_name
                visitor_info = {
                    "visitor_id": str(user.id),
                    "visitor_name": payer_name,
                    "visitor_email": user.email,
                    "visitor_phone": user.phone,
                    "booking_check_in": str(booking.check_in_date),
                    "booking_check_out": str(booking.check_out_date),
                    "booking_type": booking.booking_type if hasattr(booking, "booking_type") else None,
                }

        # Fallback: look up payer_name from student → user
        if not payer_name and p.student_id:
            from app.models.student import Student
            student_result = await db.execute(
                select(User).join(Student, Student.user_id == User.id).where(Student.id == p.student_id)
            )
            student_user = student_result.scalar_one_or_none()
            if student_user:
                payer_name = student_user.full_name

        items.append({
            "payment_id": str(p.id),
            "hostel_id": str(p.hostel_id),
            "hostel_name": hostel_name_map.get(str(p.hostel_id)),
            "booking_id": str(p.booking_id) if p.booking_id else None,
            "student_id": str(p.student_id) if p.student_id else None,
            "payer_name": payer_name,
            "amount": float(p.amount),
            "payment_type": p.payment_type,
            "payment_method": p.payment_method,
            "status": p.status,
            "transaction_id": p.gateway_payment_id or p.gateway_order_id,
            "gateway_order_id": p.gateway_order_id,
            "gateway_payment_id": p.gateway_payment_id,
            "gateway_signature": p.gateway_signature,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "failure_reason": p.failure_reason,
            "failure_code": p.failure_code,
            "receipt_url": p.receipt_url,
            "visitor": visitor_info,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 1,
    }


@router.get("/payments/{payment_id}", tags=["Payments"])
async def get_payment_detail(
    payment_id: str,
    _: SuperAdmin,
    db: DBSession,
):
    """
    **[Super Admin] Get complete details of a single payment.**

    Returns payment status, amount, transaction ID, payment date/time,
    full visitor details, booking info, and gateway metadata.
    """
    from app.models.payment import Payment
    from app.models.booking import Booking
    from app.models.user import User
    from app.models.hostel import Hostel

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    p = result.scalar_one_or_none()

    if not p:
        raise HTTPException(status_code=404, detail="Payment not found.")

    # Hostel info
    hostel_result = await db.execute(select(Hostel).where(Hostel.id == p.hostel_id))
    hostel = hostel_result.scalar_one_or_none()

    # Visitor + booking info
    visitor_info = None
    booking_info = None
    if p.booking_id:
        booking_result = await db.execute(
            select(Booking, User)
            .join(User, User.id == Booking.visitor_id)
            .where(Booking.id == p.booking_id)
        )
        row = booking_result.first()
        if row:
            booking, user = row
            visitor_info = {
                "visitor_id": str(user.id),
                "visitor_name": booking.full_name or user.full_name,
                "visitor_email": user.email,
                "visitor_phone": user.phone,
                "id_type": booking.id_type,
                "id_document_url": booking.id_document_url,
                "gender": booking.gender,
                "occupation": booking.occupation,
                "current_address": booking.current_address,
                "emergency_contact_name": booking.emergency_contact_name,
                "emergency_contact_phone": booking.emergency_contact_phone,
            }
            booking_info = {
                "booking_id": str(booking.id),
                "booking_status": booking.status.value if hasattr(booking.status, "value") else str(booking.status),
                "check_in_date": str(booking.check_in_date),
                "check_out_date": str(booking.check_out_date),
                "total_months": booking.total_months,
                "total_nights": booking.total_nights,
                "base_rent_amount": float(booking.base_rent_amount or 0),
                "security_deposit": float(booking.security_deposit or 0),
                "grand_total": float(booking.grand_total or 0),
            }

    return {
        "payment_id": str(p.id),
        "status": p.status,
        "amount": float(p.amount),
        "payment_type": p.payment_type,
        "payment_method": p.payment_method,
        "transaction_id": p.gateway_payment_id or p.gateway_order_id,
        "gateway_order_id": p.gateway_order_id,
        "gateway_payment_id": p.gateway_payment_id,
        "gateway_signature": p.gateway_signature,
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "failure_reason": p.failure_reason,
        "failure_code": p.failure_code,
        "receipt_url": p.receipt_url,
        "hostel": {
            "hostel_id": str(hostel.id) if hostel else None,
            "hostel_name": hostel.name if hostel else None,
            "city": hostel.city if hostel else None,
        },
        "visitor": visitor_info,
        "booking": booking_info,
    }


@router.get("/hostels/{hostel_id}/payments", tags=["Payments"])
async def list_hostel_payments(
    hostel_id: str,
    _: SuperAdmin,
    db: DBSession,
    payment_status: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    **[Super Admin] List all payments for a specific hostel.**

    Includes visitor name, amount, transaction ID, and payment status.
    """
    from sqlalchemy import func
    from app.models.payment import Payment
    from app.models.booking import Booking
    from app.models.user import User

    query = select(Payment).where(Payment.hostel_id == hostel_id)
    count_query = select(func.count()).select_from(Payment).where(Payment.hostel_id == hostel_id)

    if payment_status:
        query = query.where(Payment.status == payment_status)
        count_query = count_query.where(Payment.status == payment_status)

    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)

    query = query.order_by(Payment.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    payments = result.scalars().all()

    items = []
    for p in payments:
        visitor_name = None
        visitor_email = None
        if p.booking_id:
            br = await db.execute(
                select(Booking.full_name, User.email)
                .join(User, User.id == Booking.visitor_id)
                .where(Booking.id == p.booking_id)
            )
            row = br.first()
            if row:
                visitor_name, visitor_email = row

        items.append({
            "payment_id": str(p.id),
            "booking_id": str(p.booking_id) if p.booking_id else None,
            "visitor_name": visitor_name,
            "visitor_email": visitor_email,
            "amount": float(p.amount),
            "payment_type": p.payment_type,
            "payment_method": p.payment_method,
            "status": p.status,
            "transaction_id": p.gateway_payment_id or p.gateway_order_id,
            "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


from app.services.payment_config_service import PaymentConfigService
from app.schemas.payment_config import HostelPaymentConfigResponse

@router.get("/hostels/{hostel_id}/payment-config", response_model=HostelPaymentConfigResponse, tags=["Payment Settings"])
async def get_hostel_payment_config(hostel_id: str, _: SuperAdmin, db: DBSession):
    """View payment config status for a specific hostel (Super Admin only)."""
    return await PaymentConfigService(db).get_payment_config(hostel_id)