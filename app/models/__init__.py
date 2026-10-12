# Import all models in dependency order so SQLAlchemy mapper resolves relationships correctly.
# Order: user → hostel → room → booking → student → payment → operations

from app.models.user import OTPVerification, RefreshToken, User, UserRole, OTPType  # noqa: F401
from app.models.hostel import (  # noqa: F401
    AdminHostelMapping,
    Hostel,
    HostelAmenity,
    HostelImage,
    HostelStatus,
    HostelType,
    SupervisorHostelMapping,
    VisitorFavorite,
    HostelPaymentConfig,
)
from app.models.room import Bed, BedStatus, Room, RoomType  # noqa: F401
from app.models.booking import (  # noqa: F401
    BedStay,
    BedStayStatus,
    Booking,
    BookingMode,
    BookingStatus,
    BookingStatusHistory,
    CheckoutRequest,
    CheckoutRequestStatus,
    Inquiry,
    WaitlistEntry,
    WaitlistStatus,
)
from app.models.plan import Plan, PlanFeature, PlanStatus, DurationType  # noqa: F401
from app.models.student import Student, StudentStatus  # noqa: F401
from app.models.payment import Payment, PaymentWebhookEvent  # noqa: F401
from app.models.operations import (  # noqa: F401
    AttendanceRecord,
    Complaint,
    ComplaintComment,
    MaintenanceRequest,
    MessMenu,
    MessMenuItem,
    Notice,
    NoticeRead,
    Review,
    Subscription,
)
from app.models.contact import ContactLead  # noqa: F401
from app.models.billing import BillingPayment, Invoice  # noqa: F401
from app.models.transfer import StudentTransferRequest, TransferType, TransferStatus  # noqa: F401

__all__ = [
    # user
    "User", "UserRole", "OTPType", "RefreshToken", "OTPVerification",
    # hostel
    "Hostel", "HostelType", "HostelStatus",
    "HostelAmenity", "HostelImage",
    "AdminHostelMapping", "SupervisorHostelMapping", "VisitorFavorite", "HostelPaymentConfig",
    # room
    "Room", "RoomType", "Bed", "BedStatus",
    # booking
    "Booking", "BookingMode", "BookingStatus",
    "BookingStatusHistory", "CheckoutRequest", "CheckoutRequestStatus",
    "BedStay", "BedStayStatus", "Inquiry",
    "WaitlistEntry", "WaitlistStatus",
    # student
    "Student", "StudentStatus",
    # payment
    "Plan", "PlanFeature", "PlanStatus", "DurationType",
    "Payment", "PaymentWebhookEvent",
    # operations
    "Complaint", "ComplaintComment", "AttendanceRecord",
    "MaintenanceRequest", "Notice", "MessMenu", "MessMenuItem",
    "Subscription", "Review", "Notice", "NoticeRead", 
    # contact
    "ContactLead",
    # billing
    "BillingPayment", "Invoice",
]
