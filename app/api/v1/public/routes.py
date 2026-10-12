# app/api/v1/public/routes.py - COMPLETE FIXED VERSION

from typing import Annotated
from datetime import date as DateType, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile
from fastapi.responses import HTMLResponse

from app.dependencies import DBSession, CurrentUser, require_roles
from app.schemas.booking import BookingCreateRequest, BookingResponse
from app.schemas.hostel import (
    HostelDetailResponse,
    InquiryRequest,
    PaginatedHostelListResponse,
    PublicCityResponse,
    HostelRegistrationRequest,
)
from app.schemas.payment import BookingPaymentCreateRequest, BookingPaymentOrderResponse
from app.schemas.room import RoomResponse
from app.schemas.contact import ContactLeadCreate, ContactLeadResponse
from app.services.booking_service import BookingService
from app.services.hostel_service import HostelService
from app.services.payment_write_service import PaymentWriteService
from app.models.operations import Subscription
from fastapi import status


router = APIRouter()
VisitorUser = Annotated[CurrentUser, Depends(require_roles("visitor", "student", "hostel_admin", "supervisor", "super_admin"))]


def _parse_room_availability_datetime(value: str, field_name: str) -> datetime:
    """Accept both YYYY-MM-DD and ISO timestamps used by daily/hourly booking UIs."""
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be an ISO date or datetime.",
        )


def _serve_html_list(hostels: list, total: int, page: int, per_page: int) -> HTMLResponse:
    """Serve HTML response for browser requests"""
    cards_html = ""
    type_colors = {"boys": "#4361ee", "girls": "#e91e8c", "co-living": "#FF6B35", "coed": "#FF6B35"}
    
    for h in hostels[:12]:  # Limit to 12 for performance
        def g(key, default=""):
            val = h.get(key, default) if isinstance(h, dict) else getattr(h, key, default)
            return val if val is not None else default
        
        raw_ht = g("hostel_type", "")
        ht = str(raw_ht.value if hasattr(raw_ht, "value") else raw_ht).lower()
        color = type_colors.get(ht, "#FF6B35")
        name = str(g("name", "Unknown Hostel"))[:50]
        city_val = str(g("city", ""))
        state_val = str(g("state", ""))
        price = float(g("starting_monthly_price", 0) or g("starting_price", 0) or 0)
        rating = float(g("rating", 0) or 0)
        beds = int(g("available_beds", 0) or 0)
        slug = str(g("slug", ""))
        raw_desc = str(g("description", ""))
        desc = (raw_desc[:90] + "...") if len(raw_desc) > 90 else raw_desc
        stars = "★" * int(rating) + "☆" * (5 - int(rating))
        
        cards_html += f"""
        <div class="card" onclick="window.open('http://localhost:5173/hostels/{slug}','_blank')">
          <div class="card-accent" style="background:{color}"></div>
          <div class="card-type" style="background:{color}22;color:{color}">{ht.upper() or "HOSTEL"}</div>
          <h3>{name}</h3>
          <p class="location">📍 {city_val}, {state_val}</p>
          <p class="desc">{desc}</p>
          <div class="card-stats">
            <span class="stars" title="{rating}/5">{stars} <small>{rating}</small></span>
            <span class="price">₹{int(price):,}/mo</span>
          </div>
          <div class="beds">🛏 {beds} beds available</div>
        </div>"""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Levitica Nestora — Public Hostels API</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a14;color:#fff;min-height:100vh;overflow-x:hidden}}
.bg{{position:fixed;inset:0;z-index:0;pointer-events:none}}
.blob{{position:absolute;border-radius:50%;filter:blur(100px);opacity:.15;animation:float 10s ease-in-out infinite}}
.b1{{width:600px;height:600px;background:#FF6B35;top:-20%;left:-10%;animation-delay:0s}}
.b2{{width:500px;height:500px;background:#4361ee;bottom:-20%;right:-10%;animation-delay:4s}}
.b3{{width:350px;height:350px;background:#06D6A0;top:40%;left:45%;animation-delay:7s}}
@keyframes float{{0%,100%{{transform:translateY(0) scale(1)}}50%{{transform:translateY(-40px) scale(1.08)}}}}
header{{position:relative;z-index:1;padding:40px 40px 0;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}}
.logo{{display:flex;align-items:center;gap:12px;font-size:24px;font-weight:800}}
.logo-icon{{width:44px;height:44px;background:#FF6B35;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;box-shadow:0 4px 20px rgba(255,107,53,.5)}}
.logo span{{color:#FF6B35}}
.badge{{background:rgba(6,214,160,.1);border:1px solid rgba(6,214,160,.3);color:#06D6A0;padding:6px 16px;border-radius:100px;font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px}}
.dot{{width:8px;height:8px;background:#06D6A0;border-radius:50%;animation:blink 1.5s ease-in-out infinite}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.hero{{position:relative;z-index:1;text-align:center;padding:60px 40px 40px}}
.hero h1{{font-size:clamp(32px,5vw,56px);font-weight:900;line-height:1.1;background:linear-gradient(135deg,#fff 0%,rgba(255,255,255,.5) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:16px}}
.hero p{{color:rgba(255,255,255,.5);font-size:16px;max-width:500px;margin:0 auto 32px}}
.meta{{display:inline-flex;gap:24px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:16px 32px;font-size:14px;color:rgba(255,255,255,.6)}}
.meta strong{{color:#FF6B35;font-size:20px;font-weight:800;display:block}}
.grid{{position:relative;z-index:1;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px;padding:40px;max-width:1400px;margin:0 auto}}
.card{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:24px;cursor:pointer;transition:all .3s cubic-bezier(.34,1.56,.64,1);position:relative;overflow:hidden}}
.card:hover{{transform:translateY(-8px) scale(1.02);border-color:rgba(255,107,53,.4);background:rgba(255,107,53,.06);box-shadow:0 20px 60px rgba(255,107,53,.15)}}
.card-accent{{position:absolute;top:0;left:0;right:0;height:3px;border-radius:20px 20px 0 0}}
.card-type{{display:inline-block;padding:4px 12px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:.5px;margin-bottom:12px}}
.card h3{{font-size:17px;font-weight:700;margin-bottom:8px;line-height:1.3}}
.location{{font-size:13px;color:rgba(255,255,255,.4);margin-bottom:16px}}
.card-stats{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}
.stars{{color:#FFD166;font-size:13px;letter-spacing:1px}}
.price{{font-size:16px;font-weight:800;color:#FF6B35}}
.beds{{font-size:12px;color:rgba(255,255,255,.35)}}
.desc{{font-size:12px;color:rgba(255,255,255,.35);margin-bottom:14px;line-height:1.5;min-height:36px}}
footer{{position:relative;z-index:1;text-align:center;padding:40px;color:rgba(255,255,255,.2);font-size:13px;border-top:1px solid rgba(255,255,255,.05)}}
footer a{{color:#FF6B35;text-decoration:none}}
</style>
</head>
<body>
<div class="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
<header>
  <div class="logo"><div class="logo-icon">🏠</div>Stay<span>Ease</span> API</div>
  <div class="badge"><span class="dot"></span>GET /api/v1/public/hostels</div>
</header>
<div class="hero">
  <h1>Public Hostels Endpoint</h1>
  <p>Live data from the Levitica Nestora platform. Click any card to view on the frontend.</p>
  <div class="meta">
    <div><strong>{len(hostels)}</strong>hostels returned</div>
    <div><strong>v1</strong>API version</div>
    <div><strong>JSON</strong>default format</div>
  </div>
</div>
<div class="grid">{cards_html}</div>
<footer>
  <a href="/docs">📖 Swagger UI</a> &nbsp;·&nbsp;
  <a href="/redoc">📚 ReDoc</a> &nbsp;·&nbsp;
  <a href="/api/v1/public/hostels" onclick="this.href+='?_json=1'">⬇ Raw JSON</a> &nbsp;·&nbsp;
  Levitica Nestora API v1.0.0
</footer>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/hostels", response_model=PaginatedHostelListResponse)
async def list_hostels(
    request: "Request",
    db: DBSession,
    city: str | None = None,
    hostel_type: str | None = None,
    room_type: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    booking_mode: str | None = None,
    available_from: DateType | None = None,
    available_to: DateType | None = None,
    is_featured: bool | None = None,
    sort: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    **List public hostels with filters.**
    """
    if available_to and not available_from:
        raise HTTPException(status_code=400, detail="available_from is required with available_to.")
    if available_to and available_from and available_to <= available_from:
        raise HTTPException(status_code=400, detail="available_to must be after available_from.")
    try:
        result = await HostelService(db).list_public_hostels(
            city=city,
            hostel_type=hostel_type,
            room_type=room_type,
            min_price=min_price,
            max_price=max_price,
            available_from=available_from,
            available_to=available_to,
            is_featured=is_featured,
            sort=sort,
            page=page,
            page_size=per_page,
        )
        
        # Return HTML for browser requests if there are results
        accept = request.headers.get("accept", "")
        if "text/html" in accept and "application/json" not in accept and result.get("items"):
            return _serve_html_list(result.get("items", []), result.get("total", 0), page, per_page)
        
        return result
        
    except Exception as e:
        print(f"Error in list_hostels: {e}")
        import traceback
        traceback.print_exc()
        return PaginatedHostelListResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page
        )


@router.get("/hostels/search/autocomplete")
async def autocomplete(q: str, db: DBSession):
    """Location autocomplete"""
    from sqlalchemy import select, or_
    from app.models.hostel import Hostel, HostelStatus
    
    if not q or len(q) < 2:
        return []
    
    try:
        result = await db.execute(
            select(Hostel.name, Hostel.slug, Hostel.city, Hostel.state)
            .where(
                Hostel.is_public.is_(True),
                Hostel.status == HostelStatus.ACTIVE,
                or_(Hostel.name.ilike(f"%{q}%"), Hostel.city.ilike(f"%{q}%")),
            )
            .limit(10)
        )
        return [{"name": r.name, "slug": r.slug, "city": r.city, "state": r.state} for r in result.all()]
    except Exception as e:
        print(f"Autocomplete error: {e}")
        return []


@router.get("/hostels/map")
async def hostel_map_pins(db: DBSession, city: str | None = None):
    """Get hostel map pins"""
    from sqlalchemy import select
    from app.models.hostel import Hostel, HostelStatus
    
    try:
        query = select(
            Hostel.id, Hostel.name, Hostel.slug, Hostel.city,
            Hostel.latitude, Hostel.longitude, Hostel.hostel_type
        ).where(Hostel.is_public.is_(True), Hostel.status == HostelStatus.ACTIVE)
        
        if city:
            query = query.where(Hostel.city.ilike(f"%{city}%"))
        
        result = await db.execute(query)
        return [
            {"id": str(r.id), "name": r.name, "slug": r.slug, "city": r.city,
             "lat": r.latitude, "lng": r.longitude, "type": r.hostel_type}
            for r in result.all()
        ]
    except Exception as e:
        print(f"Map pins error: {e}")
        return []


@router.get("/hostels/compare")
async def compare_hostels(ids: str, db: DBSession):
    """Compare up to 4 hostels"""
    from sqlalchemy import select
    from app.models.hostel import Hostel, HostelAmenity
    
    hostel_ids = [h.strip() for h in ids.split(",")][:4]
    if not hostel_ids:
        return []
    
    result = await db.execute(select(Hostel).where(Hostel.id.in_(hostel_ids)))
    hostels = result.scalars().all()
    
    out = []
    for h in hostels:
        amenity_result = await db.execute(select(HostelAmenity.name).where(HostelAmenity.hostel_id == h.id))
        out.append({
            "id": str(h.id), "name": h.name, "slug": h.slug,
            "city": h.city, "state": h.state, "hostel_type": h.hostel_type,
            "phone": h.phone, "email": h.email,
            "is_featured": h.is_featured, "amenities": [r[0] for r in amenity_result.all()],
            "rules_and_regulations": h.rules_and_regulations,
        })
    return out


@router.get("/hostels/{slug}", response_model=HostelDetailResponse)
async def get_hostel(slug: str, db: DBSession):
    """Get full hostel detail by slug."""
    hostel = await HostelService(db).get_public_hostel(slug)
    if hostel is None:
        raise HTTPException(status_code=404, detail="Hostel not found.")
    return hostel


@router.get("/hostels/{hostel_id}/rooms", response_model=list[RoomResponse])
async def get_hostel_rooms(
    hostel_id: str,
    db: DBSession,
    booking_mode: str | None = None,
    check_in_date: str | None = None,
    check_out_date: str | None = None,
):
    """List rooms for a hostel with live availability.

    - `booking_mode=hourly` — only returns rooms with `hourly_rent > 0`
    - `booking_mode=daily`  — only returns rooms with `daily_rent > 0`
    - `booking_mode=monthly` — only returns rooms with `monthly_rent > 0` (default)
    """
    if bool(check_in_date) != bool(check_out_date):
        raise HTTPException(status_code=400, detail="Both check_in_date and check_out_date are required.")
    range_start = None
    range_end = None
    if check_in_date and check_out_date:
        range_start = _parse_room_availability_datetime(check_in_date, "check_in_date")
        range_end = _parse_room_availability_datetime(check_out_date, "check_out_date")
        if range_end <= range_start:
            raise HTTPException(status_code=400, detail="check_out_date must be after check_in_date.")
    rooms = await HostelService(db).list_hostel_rooms(
        hostel_id, start_date=range_start, end_date=range_end
    )

    # Filter out rooms that have no rate configured for the requested mode
    if booking_mode:
        mode = booking_mode.lower()
        filtered = []
        for room in rooms:
            # HostelService returns serialized room dictionaries, not ORM Room objects.
            # Attribute access here caused daily/hourly requests to return HTTP 500.
            hourly_rent = float(room.get("hourly_rent") or 0)
            daily_rent = float(room.get("daily_rent") or 0)
            monthly_rent = float(room.get("monthly_rent") or 0)
            if mode == "hourly" and hourly_rent <= 0:
                continue  # Skip ₹0/hour rooms — admin hasn't configured hourly pricing
            if mode == "daily" and daily_rent <= 0:
                continue
            if mode == "monthly" and monthly_rent <= 0:
                continue
            filtered.append(room)
        return filtered

    return rooms


@router.get("/hostels/{hostel_id}/reviews")
async def get_hostel_reviews(hostel_id: str, db: DBSession, page: int = 1, page_size: int = 20):
    """List published reviews for a hostel."""
    return await HostelService(db).list_hostel_reviews(hostel_id, page=page, page_size=page_size)


@router.get("/cities", response_model=list[PublicCityResponse])
async def list_cities(db: DBSession) -> list[PublicCityResponse]:
    """List all cities with active public hostels."""
    from sqlalchemy import select, func
    from app.models.hostel import Hostel, HostelStatus
    
    result = await db.execute(
        select(Hostel.city, func.count(Hostel.id))
        .where(Hostel.is_public.is_(True), Hostel.status == HostelStatus.ACTIVE)
        .group_by(Hostel.city)
        .order_by(Hostel.city)
    )
    cities = [{"city": row[0], "hostel_count": int(row[1] or 0)} for row in result.all()]
    return cities if cities else [
        {"city": "Hyderabad", "hostel_count": 0},
        {"city": "Bangalore", "hostel_count": 0},
        {"city": "Pune", "hostel_count": 0},
        {"city": "Mumbai", "hostel_count": 0},
    ]


@router.post("/inquiries", status_code=201)
async def create_inquiry(payload: InquiryRequest, db: DBSession):
    """Submit a hostel inquiry."""
    from app.models.booking import Inquiry
    
    inquiry = Inquiry(
        hostel_id=payload.hostel_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        message=payload.message,
    )
    db.add(inquiry)
    await db.commit()
    return {"message": "Inquiry received.", "hostel_id": payload.hostel_id}


@router.post("/contact", response_model=ContactLeadResponse, status_code=201)
async def create_contact_lead(payload: ContactLeadCreate, db: DBSession):
    """Submit a SaaS Lead Generation contact form."""
    from app.models.contact import ContactLead
    from app.services.auth_service import AuthService
    
    # Save the lead to database
    lead = ContactLead(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        organization_name=payload.organization_name,
        message=payload.message,
        inquiry_type=payload.inquiry_type,
        city=payload.city,
    )
    db.add(lead)
    await db.commit()

    # Send confirmation email
    from app.integrations.email import EmailService
    from app.config import get_settings
    from datetime import datetime, timezone, timedelta
    
    settings = get_settings()
    full_name = f"{payload.first_name} {payload.last_name or ''}".strip()
    
    # Generate IST time for the email
    ist = timezone(timedelta(hours=5, minutes=30))
    submitted_at = datetime.now(ist).strftime("%Y-%m-%d %I:%M %p IST")
    
    # Do not block response on email failure
    email_service = EmailService()
    try:
        await email_service.send_contact_lead_confirmation(
            recipient_email=payload.email,
            recipient_name=full_name,
            hostel_name=payload.organization_name or "Not Provided",
            city=payload.city or "Not Provided",
            inquiry_type=payload.inquiry_type or "Software Demo / Inquiry",
            message=payload.message,
        )
    except Exception as e:
        print(f"[Email Error] Failed to send contact confirmation to {payload.email}: {e}")
        
    try:
        await email_service.send_owner_contact_notification(
            owner_email=settings.contact_owner_email,
            first_name=payload.first_name,
            last_name=payload.last_name or "",
            organization_name=payload.organization_name or "Not Provided",
            email=payload.email,
            phone=payload.phone or "Not Provided",
            message=payload.message,
            submitted_at=submitted_at,
        )
    except Exception as e:
        print(f"[Email Error] Failed to send owner contact notification to {settings.contact_owner_email}: {e}")

    return ContactLeadResponse(message="Your inquiry has been received. Our team will contact you shortly.")


@router.post("/hostels/register", status_code=201)
async def register_hostel(
    payload: HostelRegistrationRequest,
    db: DBSession,
):
    """
    **Register a new hostel.**
    Submits a hostel application for review by super admins.
    The hostel is created with `pending_approval` status and is not public until approved.
    This endpoint is fully public and does not require authentication.
    """
    from app.services.super_admin_service import SuperAdminService
    from app.schemas.super_admin import SuperAdminHostelResponse
    
    # We use SuperAdminService.register_hostel internally
    hostel = await SuperAdminService(db).register_hostel(payload=payload, owner_id=None)
    # Convert and return using the response schema from SuperAdmin module 
    # to show all status flags (is_active, is_verified, etc.)
    return SuperAdminHostelResponse.model_validate(hostel, from_attributes=True)


@router.post("/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(
    payload: BookingCreateRequest,
    db: DBSession,
    current_user: VisitorUser,
):
    """Create a new booking request."""
    # Validate dates
    if payload.check_out_date <= payload.check_in_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="check_out_date must be after check_in_date"
        )

    return await BookingService(db).create_booking(visitor_id=current_user.id, payload=payload)


@router.get("/bookings/me", response_model=list[BookingResponse])
async def my_bookings(db: DBSession, current_user: VisitorUser):
    """List all bookings for the authenticated visitor."""
    from app.services.visitor_service import VisitorService
    return await VisitorService(db).list_bookings(current_user.id)


@router.post("/bookings/{booking_id}/payments", response_model=BookingPaymentOrderResponse, status_code=201)
async def create_booking_payment(
    booking_id: str,
    payload: BookingPaymentCreateRequest,
    db: DBSession,
    current_user: VisitorUser,
):
    """Create a Razorpay payment order for a booking."""
    return await PaymentWriteService(db).create_booking_payment(
        booking_id=booking_id,
        actor_id=current_user.id,
        payload=payload,
    )


@router.get("/hostels/{hostel_id}/subscription-status")
async def check_hostel_subscription_status(
    hostel_id: str,
    db: DBSession,
    check_in_date: str | None = None,
    check_out_date: str | None = None,
):
    """
    Check if a hostel has an active subscription for booking.
    """
    from sqlalchemy import select
    from datetime import date as date_type
    
    result = await db.execute(
        select(Subscription).where(
            Subscription.hostel_id == hostel_id,
            Subscription.status == "active"
        )
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        return {
            "can_book": False,
            "has_subscription": False,
            "message": "This hostel does not have an active subscription."
        }
    
    # Check date range if provided
    if check_in_date and check_out_date:
        try:
            check_in = date_type.fromisoformat(check_in_date)
            check_out = date_type.fromisoformat(check_out_date)
            
            if check_out > subscription.end_date:
                return {
                    "can_book": False,
                    "has_subscription": True,
                    "subscription_end_date": subscription.end_date.isoformat(),
                    "message": f"Booking dates exceed subscription expiry ({subscription.end_date})."
                }
            if check_in < subscription.start_date:
                return {
                    "can_book": False,
                    "has_subscription": True,
                    "subscription_start_date": subscription.start_date.isoformat(),
                    "message": f"Booking dates start before subscription begins ({subscription.start_date})."
                }
        except ValueError:
            pass
    
    return {
        "can_book": True,
        "has_subscription": True,
        "subscription_tier": subscription.tier,
        "subscription_start_date": subscription.start_date.isoformat(),
        "subscription_end_date": subscription.end_date.isoformat(),
        "message": "Hostel has an active subscription."
    }


@router.put("/upload-proxy")
async def upload_proxy(
    request: Request,
    filename: str,
    content_type: str,
):
    """
    Proxy upload endpoint to upload files directly to Cloudinary.
    Accepts raw binary data as the PUT body (backwards-compatible with presigned URL flow).
    """
    body = await request.body()
    from app.integrations.cloudinary_client import get_cloudinary_client
    url = await get_cloudinary_client().upload(
        file_name=filename,
        content=body,
        content_type=content_type
    )
    return {"url": url, "filename": filename, "status": "success"}


# ==================== DIRECT UPLOAD (Swagger-Testable) ====================

@router.post(
    "/upload",
    summary="Upload any file to Cloudinary",
    tags=["uploads"],
)
async def direct_upload(
    file: UploadFile = File(...),
    folder: str = "general",
):
    """
    **Upload a file directly to Cloudinary.**

    - Supports images (JPEG, PNG, WebP) and documents (PDF)
    - Max file size: 10 MB
    - Returns the permanent Cloudinary URL

    Use this endpoint in Swagger UI to test file uploads.
    The returned `url` can be stored as `profile_picture_url`, `id_document_url`, etc.
    """
    from app.integrations.cloudinary_client import get_cloudinary_client

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")

    allowed_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    ct = (file.content_type or "application/octet-stream").lower()
    if ct not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ct}'. Allowed: image/jpeg, image/png, image/webp, application/pdf.",
        )

    filename = f"{folder}/{file.filename}"
    url = await get_cloudinary_client().upload(
        file_name=filename,
        content=content,
        content_type=ct,
    )
    return {"url": url, "filename": file.filename, "content_type": ct, "status": "success"}


# ==================== NESTORA CHAT ASSISTANT AI ====================

from pydantic import BaseModel, Field

class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The message sent by the user to the assistant")

class ChatMessageResponse(BaseModel):
    reply: str = Field(..., description="The AI assistant's generated response")


@router.post(
    "/chat/message",
    response_model=ChatMessageResponse,
    summary="Ask a question to Nestora Assistant AI",
    tags=["public"],
)
async def chat_with_assistant(payload: ChatMessageRequest):
    """
    **Ask Nestora Assistant AI a question.**

    Powered by Groq's ultra-fast LPU inference using Llama 3.1.
    Free tier: 30 requests/minute, 14,400 requests/day.
    """
    import httpx
    import logging
    from app.config import get_settings

    logger = logging.getLogger(__name__)
    settings = get_settings()
    groq_key = settings.gemini_api_key  # reusing same env var slot — just set GEMINI_API_KEY to your Groq key

    if not groq_key:
        return {
            "reply": (
                "Hello! I am Nestora Assistant. "
                "My AI key is not configured yet. "
                "Please ask your admin to set the GEMINI_API_KEY environment variable."
            )
        }

    system_prompt = (
        "You are Nestora Assistant — a friendly AI chatbot for Levitica Nestora hostel management platform in India.\n\n"
        "===RULE #1 — LANGUAGE (MOST IMPORTANT RULE)===\n"
        "STRICTLY detect the script/language of the user's message and reply in EXACTLY that language.\n"
        "- Message contains English letters/words → reply in ENGLISH ONLY. NO Hindi. NO Marathi.\n"
        "- Message contains Hindi/Devanagari script → reply in Hindi.\n"
        "- Message contains Marathi words → reply in Marathi.\n"
        "NEVER switch languages. NEVER mix languages. If the user writes English, respond in English ALWAYS.\n\n"
        "===RULE #2 — CONVERSATION STYLE===\n"
        "- Be friendly and natural — like a helpful friend, not a brochure.\n"
        "- If the question is vague (like 'what to do?' or 'help'), ask ONE follow-up question:\n"
        "  Example: 'Sure! Are you asking about payments, room booking, complaints, or something else?'\n"
        "- Keep answers short — 2 to 3 sentences only.\n"
        "- Give specific step-by-step help when asked about a feature.\n\n"
        "===PLATFORM KNOWLEDGE===\n"
        "- Payments: Student Dashboard → Payments → click Pay Now\n"
        "- Book a hostel: Browse hostels → select room → complete booking → wait for admin approval\n"
        "- Complaints: Student Dashboard → Complaints → Submit new complaint\n"
        "- Mess menu: Student Dashboard → Mess Menu\n"
        "- Attendance: Managed by supervisors\n"
        "- Room change: Student Dashboard → My Hostel → Room Change Request\n"
        "- Notices: Student Dashboard → Notices\n"
        "- Profile update: Student Dashboard → My Profile\n"
    )

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {groq_key}",
    }
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload.message},
        ],
        "temperature": 0.9,
        "max_tokens": 256,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.post(url, json=body, headers=headers)
            if response.status_code == 429:
                return {"reply": "I am receiving too many requests right now. Please wait a moment and try again."}
            if response.status_code == 401:
                return {"reply": "My AI key is invalid. Please ask the admin to update the GEMINI_API_KEY in Render settings."}
            if response.status_code != 200:
                logger.error(f"Groq API error {response.status_code}: {response.text}")
                return {"reply": "I am having trouble connecting right now. Please try again in a moment."}

            resp_json = response.json()
            try:
                reply = resp_json["choices"][0]["message"]["content"]
                return {"reply": reply.strip()}
            except (KeyError, IndexError) as parse_err:
                logger.error(f"Failed to parse Groq response: {parse_err}. Response: {resp_json}")
                return {"reply": "I received an empty response. Could you rephrase your question?"}
        except Exception as e:
            logger.error(f"Groq API connection error: {e}")
            return {"reply": "Sorry, I am offline right now. Please try again later."}


