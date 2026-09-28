"""
Levitica Nestora - Complete Seed Data Script
Run: python -m scripts.seed_data --clean (from hostel-management-api/)
Populates: users, hostels, rooms, beds, bookings, students, payments,
           mess menus, notices, complaints, attendance, maintenance, reviews.
"""
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.core.database import Base
from app.core.security import hash_password
from app.models.booking import (
    BedStay, BedStayStatus, Booking, BookingMode,
    BookingStatus, BookingStatusHistory, Inquiry, WaitlistEntry, WaitlistStatus,
)
from app.models.hostel import (
    AdminHostelMapping, Hostel, HostelAmenity,
    HostelImage, HostelStatus, SupervisorHostelMapping,
)
from app.models.operations import (
    AttendanceRecord, Complaint, ComplaintComment,
    MaintenanceRequest, MessMenu, MessMenuItem,
    Notice, Review, Subscription,
)
from app.models.payment import Payment
from app.models.room import Bed, BedStatus, Room, RoomType
from app.models.student import Student, StudentStatus
from app.models.user import User, UserRole

settings = get_settings()

# ---------------------------------------------------------------------------
# Realistic Unsplash image URLs (free, no auth needed)
# ---------------------------------------------------------------------------
HOSTEL_IMAGES = {
    "Green Valley Boys Hostel": [
        "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?w=800",
        "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=800",
        "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800",
    ],
    "Pearl Girls Hostel": [
        "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=800",
        "https://images.unsplash.com/photo-1540518614846-7eded433c457?w=800",
        "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800",
    ],
    "Sunrise Co-ed Hostel": [
        "https://images.unsplash.com/photo-1564078516393-cf04bd966897?w=800",
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
        "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800",
    ],
    "Metro Stay Hostel": [
        "https://images.unsplash.com/photo-1571508601891-ca5e7a713859?w=800",
        "https://images.unsplash.com/photo-1595526114035-0d45ed16cfbf?w=800",
        "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=800",
    ],
}

# ---------------------------------------------------------------------------
# Full 7-day × 4-meal mess menu data (realistic Indian hostel food)
# ---------------------------------------------------------------------------
MESS_MENU = [
    # Monday
    ("Monday", "breakfast", "Idli Sambar with Coconut Chutney", True, None),
    ("Monday", "lunch", "Steamed Rice, Dal Tadka, Aloo Gobi, Papad", True, None),
    ("Monday", "snacks", "Bread Pakora with Mint Chutney", True, None),
    ("Monday", "dinner", "Chapati, Paneer Butter Masala, Jeera Rice, Salad", True, None),
    # Tuesday
    ("Tuesday", "breakfast", "Poha with Sev and Lemon", True, None),
    ("Tuesday", "lunch", "Chicken Biryani, Raita, Boiled Egg", False, "Non-veg day"),
    ("Tuesday", "snacks", "Samosa with Tamarind Chutney", True, None),
    ("Tuesday", "dinner", "Roti, Dal Makhani, Bhindi Fry, Rice", True, None),
    # Wednesday
    ("Wednesday", "breakfast", "Upma with Coconut Chutney", True, None),
    ("Wednesday", "lunch", "Rice, Rajma Masala, Cucumber Raita, Pickle", True, None),
    ("Wednesday", "snacks", "Veg Cutlet with Ketchup", True, None),
    ("Wednesday", "dinner", "Chapati, Egg Curry, Steamed Rice, Salad", False, "Egg available"),
    # Thursday
    ("Thursday", "breakfast", "Dosa with Sambar and Chutney", True, None),
    ("Thursday", "lunch", "Mutton Curry, Rice, Dal, Papad", False, "Non-veg day"),
    ("Thursday", "snacks", "Pav Bhaji", True, None),
    ("Thursday", "dinner", "Roti, Chana Masala, Jeera Rice, Curd", True, None),
    # Friday
    ("Friday", "breakfast", "Aloo Paratha with Curd and Pickle", True, None),
    ("Friday", "lunch", "Veg Pulao, Raita, Mixed Veg Curry, Papad", True, None),
    ("Friday", "snacks", "Maggi Noodles", True, "Special Friday snack"),
    ("Friday", "dinner", "Chapati, Fish Curry, Rice, Salad", False, "Fish Friday"),
    # Saturday
    ("Saturday", "breakfast", "Chole Bhature", True, "Weekend special"),
    ("Saturday", "lunch", "Chicken Fried Rice, Manchurian, Soup", False, "Weekend special"),
    ("Saturday", "snacks", "Fruit Chaat", True, None),
    ("Saturday", "dinner", "Biryani, Raita, Mirchi Ka Salan, Dessert", False, "Weekend feast"),
    # Sunday
    ("Sunday", "breakfast", "Puri Sabzi with Halwa", True, "Sunday special"),
    ("Sunday", "lunch", "Dal Baati Churma", True, "Rajasthani special"),
    ("Sunday", "snacks", "Ice Cream / Kulfi", True, "Sunday treat"),
    ("Sunday", "dinner", "Paneer Tikka Masala, Naan, Rice, Kheer", True, "Sunday feast"),
]

# ---------------------------------------------------------------------------
# Hostel configurations
# ---------------------------------------------------------------------------
HOSTELS_CONFIG = [
    {
        "name": "Green Valley Boys Hostel",
        "slug": "green-valley-boys-hostel",
        "city": "Hyderabad",
        "state": "Telangana",
        "hostel_type": "BOYS",
        "description": (
            "Green Valley Boys Hostel is a premium accommodation for male students and "
            "working professionals in the heart of Hyderabad. Surrounded by lush greenery, "
            "we offer a peaceful environment with all modern amenities."
        ),
        "address_line1": "Plot 45, Green Valley Road, Madhapur",
        "address_line2": "Near Hitech City Metro Station",
        "pincode": "500081",
        "latitude": 17.4474,
        "longitude": 78.3762,
        "phone": "+91-9876543210",
        "email": "greenvalley@leviticanestora.in",
        "website": "https://greenvalley.leviticanestora.in",
        "rules": (
            "1. Visitors allowed only in common areas between 9 AM - 8 PM.\n"
            "2. No smoking or alcohol on premises.\n"
            "3. Lights out by 11 PM on weekdays.\n"
            "4. Mess timings: Breakfast 7-9 AM, Lunch 12-2 PM, Dinner 8-10 PM."
        ),
        "is_featured": True,
        "amenities": [
            ("WiFi", "connectivity"), ("Study Room", "facilities"),
            ("Laundry", "facilities"), ("Gym", "facilities"),
            ("CCTV", "safety"), ("Security Guard", "safety"),
            ("Parking", "facilities"), ("Power Backup", "utilities"),
        ],
        "rooms": [
            {"number": "101", "floor": 1, "type": "SINGLE", "beds": 1, "daily": 900, "monthly": 8500, "deposit": 8500},
            {"number": "102", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 700, "monthly": 6500, "deposit": 6500},
            {"number": "103", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 700, "monthly": 6500, "deposit": 6500},
            {"number": "201", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 600, "monthly": 5500, "deposit": 5500},
            {"number": "202", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 600, "monthly": 5500, "deposit": 5500},
            {"number": "203", "floor": 2, "type": "DORMITORY", "beds": 6, "daily": 400, "monthly": 3500, "deposit": 3500},
            {"number": "301", "floor": 3, "type": "SINGLE", "beds": 1, "daily": 950, "monthly": 9000, "deposit": 9000},
        ],
    },
    {
        "name": "Pearl Girls Hostel",
        "slug": "pearl-girls-hostel",
        "city": "Bangalore",
        "state": "Karnataka",
        "hostel_type": "GIRLS",
        "description": (
            "Pearl Girls Hostel is a safe, comfortable, and well-managed accommodation "
            "exclusively for women in Bangalore. Located in Koramangala, we are minutes "
            "away from major IT parks and colleges."
        ),
        "address_line1": "12/3, 5th Block, Koramangala",
        "address_line2": "Near Forum Mall, Bangalore",
        "pincode": "560095",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "phone": "+91-9876543211",
        "email": "pearl@leviticanestora.in",
        "website": "https://pearl.leviticanestora.in",
        "rules": (
            "1. Male visitors strictly not allowed beyond reception.\n"
            "2. Gate closes at 10 PM. Late entry requires prior permission.\n"
            "3. No cooking in rooms. Use common kitchen only.\n"
            "4. Mess timings: Breakfast 7-9 AM, Lunch 12-2 PM, Dinner 8-10 PM."
        ),
        "is_featured": True,
        "amenities": [
            ("WiFi", "connectivity"), ("Reading Room", "facilities"),
            ("Laundry", "facilities"), ("Rooftop Garden", "recreation"),
            ("CCTV", "safety"), ("Biometric Entry", "safety"),
            ("Power Backup", "utilities"), ("Housekeeping", "services"),
        ],
        "rooms": [
            {"number": "A101", "floor": 1, "type": "SINGLE", "beds": 1, "daily": 1000, "monthly": 9500, "deposit": 9500},
            {"number": "A102", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 800, "monthly": 7500, "deposit": 7500},
            {"number": "A103", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 800, "monthly": 7500, "deposit": 7500},
            {"number": "B201", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 650, "monthly": 6000, "deposit": 6000},
            {"number": "B202", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 650, "monthly": 6000, "deposit": 6000},
            {"number": "C301", "floor": 3, "type": "SINGLE", "beds": 1, "daily": 1050, "monthly": 10000, "deposit": 10000},
        ],
    },
    {
        "name": "Sunrise Co-ed Hostel",
        "slug": "sunrise-co-ed-hostel",
        "city": "Pune",
        "state": "Maharashtra",
        "hostel_type": "co-living",
        "description": (
            "Sunrise Co-ed Hostel is a modern, vibrant accommodation for students and "
            "young professionals in Pune. Located in Kothrud, we offer separate floors "
            "for male and female residents."
        ),
        "address_line1": "Survey No. 78, Kothrud",
        "address_line2": "Near Kothrud Bus Stand, Pune",
        "pincode": "411038",
        "latitude": 18.5074,
        "longitude": 73.8077,
        "phone": "+91-9876543212",
        "email": "sunrise@leviticanestora.in",
        "website": "https://sunrise.leviticanestora.in",
        "rules": (
            "1. Separate floors for male and female residents.\n"
            "2. Common areas accessible to all residents.\n"
            "3. No alcohol or drugs on premises.\n"
            "4. Mess timings: Breakfast 7-9 AM, Lunch 12-2 PM, Dinner 8-10 PM."
        ),
        "is_featured": True,
        "amenities": [
            ("WiFi", "connectivity"), ("Gym", "recreation"),
            ("Indoor Games", "recreation"), ("Rooftop Terrace", "recreation"),
            ("Laundry", "facilities"), ("CCTV", "safety"),
            ("Power Backup", "utilities"), ("Cafeteria", "food"),
        ],
        "rooms": [
            {"number": "M101", "floor": 1, "type": "SINGLE", "beds": 1, "daily": 850, "monthly": 8000, "deposit": 8000},
            {"number": "M102", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 650, "monthly": 6000, "deposit": 6000},
            {"number": "M201", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 550, "monthly": 5000, "deposit": 5000},
            {"number": "M202", "floor": 2, "type": "DORMITORY", "beds": 6, "daily": 380, "monthly": 3200, "deposit": 3200},
            {"number": "F301", "floor": 3, "type": "SINGLE", "beds": 1, "daily": 900, "monthly": 8500, "deposit": 8500},
            {"number": "F302", "floor": 3, "type": "DOUBLE", "beds": 2, "daily": 700, "monthly": 6500, "deposit": 6500},
        ],
    },
    {
        "name": "Metro Stay Hostel",
        "slug": "metro-stay-hostel",
        "city": "Mumbai",
        "state": "Maharashtra",
        "hostel_type": "COED",
        "description": (
            "Metro Stay Hostel is a premium co-ed hostel in the heart of Mumbai, "
            "offering unmatched connectivity and comfort. Located in Andheri West, "
            "we are a 5-minute walk from the metro station."
        ),
        "address_line1": "14, Versova Road, Andheri West",
        "address_line2": "Near Andheri Metro Station, Mumbai",
        "pincode": "400058",
        "latitude": 19.1136,
        "longitude": 72.8697,
        "phone": "+91-9876543213",
        "email": "metro@leviticanestora.in",
        "website": "https://metro.leviticanestora.in",
        "rules": (
            "1. AC rooms — do not tamper with AC settings.\n"
            "2. Gate closes at 11 PM. Late entry via security intercom.\n"
            "3. No cooking in rooms. Use common kitchen.\n"
            "4. Mess timings: Breakfast 7-9 AM, Lunch 12-2 PM, Dinner 8-10 PM."
        ),
        "is_featured": False,
        "amenities": [
            ("WiFi", "connectivity"), ("AC Rooms", "comfort"),
            ("Common Kitchen", "facilities"), ("Laundry", "facilities"),
            ("CCTV", "safety"), ("Security Guard", "safety"),
            ("Power Backup", "utilities"), ("Elevator", "facilities"),
        ],
        "rooms": [
            {"number": "101", "floor": 1, "type": "SINGLE", "beds": 1, "daily": 1200, "monthly": 12000, "deposit": 12000},
            {"number": "102", "floor": 1, "type": "DOUBLE", "beds": 2, "daily": 950, "monthly": 9000, "deposit": 9000},
            {"number": "201", "floor": 2, "type": "SINGLE", "beds": 1, "daily": 1300, "monthly": 13000, "deposit": 13000},
            {"number": "202", "floor": 2, "type": "DOUBLE", "beds": 2, "daily": 1000, "monthly": 9500, "deposit": 9500},
            {"number": "203", "floor": 2, "type": "TRIPLE", "beds": 3, "daily": 800, "monthly": 7500, "deposit": 7500},
            {"number": "301", "floor": 3, "type": "DORMITORY", "beds": 5, "daily": 550, "monthly": 5000, "deposit": 5000},
        ],
    },
]

# ---------------------------------------------------------------------------
# Student / visitor names (63 students from employee data - single definition)
# ---------------------------------------------------------------------------
EMPLOYEE_DATA = [
    ("LEV029", "Abhilash Gurrampally", "Mani Kiran Kopanathi"),
    ("LEV039", "Anusha Enigalla", "Durgaprasad Medipudi"),
    ("LEV122", "Aravelly Tharun", "Anusha Enigalla"),
    ("LEV047", "Ashok Kota", "Sameer Shaik"),
    ("LEV121", "Baluguri Ashritha Rao", "Durgaprasad Medipudi"),
    ("LEV116", "Bhargava Sai Kolli", "Kallamadi Kranti Kumar Reddy"),
    ("LEV027", "Bogala Chandramouli", "Durgaprasad Medipudi"),
    ("LEV023", "Burri Gowtham", "Mani Kiran Kopanathi"),
    ("LEV001", "Chandu Thota", "Durgaprasad Medipudi"),
    ("LEV038", "Cheekati Abhinaya", "Durgaprasad Medipudi"),
    ("LEV014", "Chodisetti Sri Rama Sai", "Mani Kiran Kopanathi"),
    ("LEV123", "Dhanikela Brahmam", "Anusha Enigalla"),
    ("LEV012", "Dheeraj Krishna Jakkula", "Mani Kiran Kopanathi"),
    ("LEV028", "Dorasala Nagendra Reddy", "Mani Kiran Kopanathi"),
    ("LEV017", "Dubbaka Bharath", "Sameer Shaik"),
    ("LEV026", "Durga Sai Vara Prasad Chandragiri", "Durgaprasad Medipudi"),
    ("LEV031", "Gorle Leela Sai Kumar", "Durgaprasad Medipudi"),
    ("LEV127", "Gubba Vasini", "Anusha Enigalla"),
    ("LEV005", "Gurajapu Pavani", "Nagendra Uggirala"),
    ("LEV118", "Hari Charan Teja Gudapati", "Anusha Enigalla"),
    ("LEV050", "Harsha Vardhan Naidu Dasireddy", "Kallamadi Kranti Kumar Reddy"),
    ("LEV044", "Hemant Tukaram Pawade", "Mani Kiran Kopanathi"),
    ("LEV008", "Hruthik Venkata Sai Ganesh Jamanu", "Chandu Thota"),
    ("LEV033", "Jagadeesh Bedolla", "Sameer Shaik"),
    ("LEV128", "Jothi Lakshmi A", "Anusha Enigalla"),
    ("LEV013", "Kallamadi Kowsik Reddy", "Durgaprasad Medipudi"),
    ("LEV011", "Kallamadi Kranti Kumar Reddy", "Durgaprasad Medipudi"),
    ("LEV004", "Kallamadi Keerthi", "Nagendra Uggirala"),
    ("LEV003", "Kandepuneni Swetha Naga Durga", "Chandu Thota"),
    ("LEV036", "Kasarapu Rajeswar Reddy", "Sameer Shaik"),
    ("LEV019", "Keerthi Ranjani Maddala", "Sameer Shaik"),
    ("LEV032", "Khuswanth Rao Jadav", "Sameer Shaik"),
    ("LEV034", "Kishore Tiruveedhula", "Mani Kiran Kopanathi"),
    ("LEV046", "Kondareddy Revathi", "Sameer Shaik"),
    ("LEV126", "Korada Kavya", "Anusha Enigalla"),
    ("LEV035", "Kothapalli Sai Avinash Varma", "Mani Kiran Kopanathi"),
    ("LEV048", "Lokeshwar Reddy Kondappagari", "Kallamadi Kranti Kumar Reddy"),
    ("LEV010", "Mani Kiran Kopanathi", "Durgaprasad Medipudi"),
    ("LEV041", "Manikanta Nedunuri", "Mani Kiran Kopanathi"),
    ("LEV120", "Medipudi Durgaprasad", None),
    ("LEV002", "Minal Devidas Mahajan", "Durgaprasad Medipudi"),
    ("LEV041", "Mohammad Aslam Yakub Khan", "Durgaprasad Medipudi"),
    ("LEV042", "Muniganti Sai Sumiran", "Sameer Shaik"),
    ("LEV117", "N Sairam Srinivasa Chakravarthi Pothureddy", "Kallamadi Kranti Kumar Reddy"),
    ("LEV040", "Nagadurga Sarnala", "Mani Kiran Kopanathi"),
    ("LEV024", "Nagendra Uggirala", "Durgaprasad Medipudi"),
    ("LEV015", "Nani Venkata Ravi Teja Maddala", "Sameer Shaik"),
    ("LEV022", "Naveen Sai Koppereddy", "Nagendra Uggirala"),
    ("LEV025", "Nollu Lalith Kumar", "Sameer Shaik"),
    ("LEV021", "Pagadala Anitha", "Sameer Shaik"),
    ("LEV018", "Peddireddy Sai Kumar Reddy", "Sameer Shaik"),
    ("LEV037", "Pesaru Kireeti", "Sameer Shaik"),
    ("LEV049", "Pillala Sukanya", "Kallamadi Kranti Kumar Reddy"),
    ("LEV006", "Potnuri Naveen Bhargav", "Chandu Thota"),
    ("LEV051", "Pradeep Bantapalli", "Kallamadi Kranti Kumar Reddy"),
    ("LEV016", "Pramod Kumar Sindhe", "Sameer Shaik"),
    ("LEV009", "Sameer Shaik", "Durgaprasad Medipudi"),
    ("LEV030", "Sasi Kumar Reddy Chintala", "Mani Kiran Kopanathi"),
    ("LEV043", "Satya Kiran Chelluboina", "Mani Kiran Kopanathi"),
    ("LEV124", "Sumathi Mittapalli", "Anusha Enigalla"),
    ("LEV007", "Syed Afran Ali", "Chandu Thota"),
    ("LEV119", "Vamshi Hasanabada", "Kallamadi Kranti Kumar Reddy"),
    ("LEV125", "Vijay Ram Maddukuri", "Anusha Enigalla"),
]

def _emp_email_prefix(name: str, code: str) -> str:
    """Generate email prefix from name + employee code."""
    parts = name.lower().split()
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}.{code.lower()}"
    return f"{parts[0]}.{code.lower()}"

STUDENT_NAMES = [(emp[1], _emp_email_prefix(emp[1], emp[0])) for emp in EMPLOYEE_DATA]

VISITOR_NAMES = [
    ("Arun Kapoor", "arun.kapoor"),
    ("Sunita Bose", "sunita.bose"),
    ("Manoj Yadav", "manoj.yadav"),
    ("Rekha Mishra", "rekha.mishra"),
    ("Tarun Saxena", "tarun.saxena"),
    ("Geeta Pandey", "geeta.pandey"),
    ("Harish Nambiar", "harish.nambiar"),
    ("Swati Kulkarni", "swati.kulkarni"),
    ("Rajesh Dubey", "rajesh.dubey"),
    ("Anjali Sinha", "anjali.sinha"),
]

COMPLAINT_DATA = [
    ("maintenance", "Water leakage in bathroom", "Continuous water leakage from bathroom tap. Wasting a lot of water.", "high"),
    ("food", "Mess food quality declined", "Food quality has declined. Dal is undercooked.", "medium"),
    ("electricity", "Power socket not working", "Power socket near my bed is not working.", "medium"),
    ("cleanliness", "Common bathroom not cleaned", "Common bathroom not cleaned for 2 days.", "high"),
    ("wifi", "WiFi speed very slow", "WiFi speed is extremely slow. Cannot attend online classes.", "low"),
    ("security", "Main gate left open at night", "Main gate was found open at 2 AM. Security concern.", "high"),
]

NOTICE_DATA = [
    ("Mess Menu Update", "Updated mess menu for this week. Sunday special includes Biryani.", "general", "medium"),
    ("Water Supply Interruption - Sunday 6 AM to 10 AM", "Due to maintenance, water supply will be interrupted.", "maintenance", "high"),
    ("Hostel Day Celebration - April 5th", "Cultural programs, sports, and special dinner. All residents invited.", "event", "medium"),
    ("Visitor Policy Reminder", "Visitors allowed only in common areas between 9 AM and 8 PM.", "policy", "medium"),
]

MAINTENANCE_DATA = [
    ("plumbing", "Bathroom pipe burst", "Main water pipe in bathroom has burst.", "emergency", True),
    ("electrical", "Short circuit in corridor lights", "Corridor lights have short circuit.", "high", True),
    ("carpentry", "Broken door hinge", "Door hinge is broken. Door doesn't close properly.", "medium", False),
    ("plumbing", "Clogged drain", "Drain in common bathroom is clogged.", "high", False),
]

# ---------------------------------------------------------------------------
# Seeder class
# ---------------------------------------------------------------------------
class LeviticaNestoraSeeder:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users: dict[str, str] = {}
        self.hostels: dict[str, str] = {}
        self.rooms: dict[str, dict] = {}
        self.beds: dict[str, dict] = {}
        self.students: dict[str, str] = {}
        self.bookings: list[Booking] = []

    def _uid(self) -> uuid.UUID:
        return uuid.uuid4()

    async def _flush(self):
        await self.session.flush()

    async def create_user(self, email: str, phone: str, full_name: str,
                          role: UserRole, password: str = "Test@1234") -> str:
        existing = await self.session.execute(select(User).where(User.email == email))
        user_obj = existing.scalar_one_or_none()
        if user_obj:
            self.users[email] = user_obj.id
            return user_obj.id

        user = User(
            id=self._uid(), email=email, phone=phone, full_name=full_name,
            password_hash=hash_password(password), role=role,
            is_active=True, is_email_verified=True, is_phone_verified=True,
        )
        self.session.add(user)
        await self._flush()
        self.users[email] = user.id
        print(f"  ✓ {role.value:15s} {full_name} ({email})")
        return user.id

    async def create_hostel(self, cfg: dict, admin_id: str, supervisor_id: str) -> str:
        existing = await self.session.execute(select(Hostel).where(Hostel.slug == cfg["slug"]))
        hostel_obj = existing.scalar_one_or_none()
        if hostel_obj:
            self.hostels[cfg["name"]] = hostel_obj.id
            return hostel_obj.id

        hostel = Hostel(
            id=self._uid(),
            name=cfg["name"], slug=cfg["slug"],
            description=cfg["description"],
            hostel_type=cfg["hostel_type"],
            status=HostelStatus.ACTIVE,
            address_line1=cfg["address_line1"],
            address_line2=cfg["address_line2"],
            city=cfg["city"], state=cfg["state"],
            country="India", pincode=cfg["pincode"],
            latitude=cfg["latitude"], longitude=cfg["longitude"],
            phone=cfg["phone"], email=cfg["email"],
            website=cfg.get("website"),
            is_featured=cfg.get("is_featured", False),
            is_public=True,
            rules_and_regulations=cfg["rules"],
        )
        self.session.add(hostel)
        await self._flush()
        self.hostels[cfg["name"]] = hostel.id

        self.session.add(AdminHostelMapping(
            id=self._uid(), admin_id=admin_id, hostel_id=hostel.id,
            is_primary=True, assigned_by=admin_id,
        ))
        self.session.add(SupervisorHostelMapping(
            id=self._uid(), supervisor_id=supervisor_id,
            hostel_id=hostel.id, assigned_by=admin_id,
        ))

        for name, category in cfg["amenities"]:
            self.session.add(HostelAmenity(
                id=self._uid(), hostel_id=hostel.id,
                name=name, category=category,
            ))

        images = HOSTEL_IMAGES.get(cfg["name"], [])
        for i, url in enumerate(images):
            self.session.add(HostelImage(
                id=self._uid(), hostel_id=hostel.id,
                url=url,
                thumbnail_url=url.replace("w=800", "w=400"),
                caption=f"{cfg['name']} - Photo {i+1}",
                image_type="gallery",
                sort_order=i,
                is_primary=(i == 0),
            ))

        await self._flush()
        print(f"  ✓ Hostel: {cfg['name']} ({cfg['city']})")
        return hostel.id

    async def create_rooms_and_beds(self, hostel_id: str, rooms_cfg: list) -> None:
        for r in rooms_cfg:
            existing_room_res = await self.session.execute(
                select(Room).where(Room.hostel_id == hostel_id, Room.room_number == r["number"])
            )
            existing_room = existing_room_res.scalar_one_or_none()
            if existing_room:
                room = existing_room
            else:
                room = Room(
                    id=self._uid(), hostel_id=hostel_id,
                    room_number=r["number"], floor=r["floor"],
                    room_type=r["type"],
                    total_beds=r["beds"],
                    daily_rent=r["daily"], monthly_rent=r["monthly"],
                    security_deposit=r["deposit"],
                    dimensions=r.get("dim"), is_active=True,
                )
                self.session.add(room)
                await self._flush()

            self.rooms[room.id] = {"hostel_id": hostel_id, "room_id": room.id}

            for b in range(1, r["beds"] + 1):
                bed_number = f"B{b}"
                existing_bed_res = await self.session.execute(
                    select(Bed).where(Bed.room_id == room.id, Bed.bed_number == bed_number)
                )
                existing_bed = existing_bed_res.scalar_one_or_none()
                if existing_bed:
                    self.beds[existing_bed.id] = {
                        "hostel_id": hostel_id,
                        "room_id": room.id,
                        "bed_id": existing_bed.id,
                        "bed_number": bed_number,
                    }
                    continue

                bed = Bed(
                    id=self._uid(), hostel_id=hostel_id,
                    room_id=room.id,
                    bed_number=bed_number,
                    status=BedStatus.AVAILABLE,
                )
                self.session.add(bed)
                await self._flush()
                self.beds[bed.id] = {
                    "hostel_id": hostel_id,
                    "room_id": room.id,
                    "bed_id": bed.id,
                    "bed_number": bed_number,
                }

    async def create_booking(self, visitor_id: str, hostel_id: str,
                             room_id: str, bed_id: str | None,
                             status: BookingStatus,
                             mode: BookingMode = BookingMode.MONTHLY,
                             days: int = 30,
                             full_name: str = "Test Visitor",
                             approved_by: str | None = None) -> Booking:
        check_in = date.today() - timedelta(days=5)
        check_out = check_in + timedelta(days=days)
        monthly_rent = 6000.0
        booking_advance = monthly_rent * 0.25

        booking = Booking(
            id=self._uid(),
            booking_number=f"SE-{uuid.uuid4().hex[:8].upper()}",
            visitor_id=visitor_id,
            hostel_id=hostel_id,
            room_id=room_id,
            bed_id=bed_id,
            booking_mode=mode,
            status=status,
            check_in_date=check_in,
            check_out_date=check_out,
            total_nights=days if mode == BookingMode.DAILY else None,
            total_months=1 if mode == BookingMode.MONTHLY else None,
            base_rent_amount=monthly_rent,
            security_deposit=6000.0,
            booking_advance=booking_advance,
            grand_total=monthly_rent + 6000.0,
            full_name=full_name,
            date_of_birth=date(2000, 6, 15),
            gender="M",
            occupation="Student",
            institution="University",
            current_address="123 Main Street",
            id_type="aadhar",
            emergency_contact_name="Parent",
            emergency_contact_phone="+91-9000000099",
            emergency_contact_relationship="Parent",
            approved_by=approved_by,
        )
        self.session.add(booking)
        await self._flush()

        self.session.add(BookingStatusHistory(
            id=self._uid(), booking_id=booking.id,
            old_status=None, new_status=status,
            changed_by=visitor_id,
            note=f"Booking created with status {status.value}",
        ))

        if status in (BookingStatus.APPROVED, BookingStatus.CHECKED_IN) and bed_id:
            self.session.add(BedStay(
                id=self._uid(), hostel_id=hostel_id,
                bed_id=bed_id, booking_id=booking.id,
                student_id=None,
                start_date=check_in, end_date=check_out,
                status=BedStayStatus.ACTIVE if status == BookingStatus.CHECKED_IN else BedStayStatus.RESERVED,
            ))

        await self._flush()
        self.bookings.append(booking)
        return booking

    async def create_student(self, user_id: str, hostel_id: str,
                             room_id: str, bed_id: str,
                             booking_id: str, idx: int,
                             employee_code: str | None = None) -> str:
        existing_student = await self.session.execute(select(Student).where(Student.user_id == user_id))
        s_obj = existing_student.scalar_one_or_none()
        if s_obj:
            self.students[user_id] = s_obj.id
            return s_obj.id

        if employee_code:
            student_number = f"{employee_code}-{idx:02d}"
        else:
            student_number = f"SE{2026}{idx:04d}"
        student = Student(
            id=self._uid(), user_id=user_id,
            hostel_id=hostel_id, room_id=room_id,
            bed_id=bed_id, booking_id=booking_id,
            student_number=student_number,
            check_in_date=date.today() - timedelta(days=30),
            check_out_date=None,
            status=StudentStatus.ACTIVE,
        )
        self.session.add(student)
        await self._flush()
        self.students[user_id] = student.id
        return student.id

    async def create_payment(self, hostel_id: str, booking_id: str | None,
                             student_id: str | None, amount: float,
                             ptype: str = "booking_advance",
                             status: str = "captured") -> None:
        self.session.add(Payment(
            id=self._uid(), hostel_id=hostel_id,
            booking_id=booking_id, student_id=student_id,
            amount=amount, payment_type=ptype,
            payment_method="razorpay",
            gateway_order_id=f"order_{uuid.uuid4().hex[:12]}",
            gateway_payment_id=f"pay_{uuid.uuid4().hex[:12]}" if status == "captured" else None,
            gateway_signature=f"sig_{uuid.uuid4().hex[:24]}" if status == "captured" else None,
            status=status,
            due_date=date.today(),
            paid_at=datetime.now(UTC) if status == "captured" else None,
        ))
        await self._flush()

    async def create_mess_menu(self, hostel_id: str, created_by: str) -> None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        menu = MessMenu(
            id=self._uid(), hostel_id=hostel_id,
            week_start_date=week_start,
            is_active=True, created_by=created_by,
        )
        self.session.add(menu)
        await self._flush()
        for day, meal, item, is_veg, note in MESS_MENU:
            self.session.add(MessMenuItem(
                id=self._uid(), menu_id=menu.id,
                day_of_week=day, meal_type=meal,
                item_name=item, is_veg=is_veg,
                special_note=note,
            ))
        await self._flush()

    async def create_notices(self, hostel_id: str, created_by: str) -> None:
        for title, content, ntype, priority in NOTICE_DATA:
            self.session.add(Notice(
                id=self._uid(), hostel_id=hostel_id,
                title=title, content=content,
                notice_type=ntype, priority=priority,
                is_published=True, created_by=created_by,
            ))
        await self._flush()

    async def create_complaints(self, hostel_id: str,
                                student_ids: list[str],
                                supervisor_id: str) -> None:
        for i, (cat, title, desc, priority) in enumerate(COMPLAINT_DATA):
            student_id = student_ids[i % len(student_ids)]
            complaint = Complaint(
                id=self._uid(),
                complaint_number=f"CMP-{uuid.uuid4().hex[:6].upper()}",
                student_id=student_id, hostel_id=hostel_id,
                category=cat, title=title, description=desc,
                priority=priority,
                status="resolved" if i % 3 == 0 else ("in_progress" if i % 3 == 1 else "open"),
                assigned_to=supervisor_id if i % 2 == 0 else None,
                resolution_notes="Issue resolved by maintenance team." if i % 3 == 0 else None,
            )
            self.session.add(complaint)
            await self._flush()
            self.session.add(ComplaintComment(
                id=self._uid(), complaint_id=complaint.id,
                author_id=supervisor_id,
                content="We have received your complaint and are looking into it.",
            ))
        await self._flush()

    async def create_attendance(self, hostel_id: str,
                                student_ids: list[str],
                                supervisor_id: str) -> None:
        statuses = ["present", "present", "present", "late", "absent"]
        seen: set[tuple] = set()
        
        for student_id in student_ids:
            for days_ago in range(14):
                d = date.today() - timedelta(days=days_ago)
                key = (student_id, d)
                if key in seen:
                    continue
                seen.add(key)
                
                # Check if attendance record already exists
                stmt = select(AttendanceRecord).where(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.date == d
                )
                result = await self.session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    continue
                    
                st = statuses[days_ago % len(statuses)]
                record = AttendanceRecord(
                    id=self._uid(),
                    student_id=student_id,
                    hostel_id=hostel_id,
                    date=d,
                    check_in_time=time(9, 0) if st != "absent" else None,
                    check_out_time=time(22, 0) if st == "present" else None,
                    status=st,
                    marked_by=supervisor_id,
                    method="manual",
                    remarks="Late arrival" if st == "late" else None,
                )
                self.session.add(record)
        await self._flush()

    async def create_maintenance(self, hostel_id: str,
                                 room_ids: list[str],
                                 supervisor_id: str,
                                 admin_id: str) -> None:
        for i, (cat, title, desc, priority, needs_approval) in enumerate(MAINTENANCE_DATA):
            room_id = room_ids[i % len(room_ids)] if room_ids else None
            self.session.add(MaintenanceRequest(
                id=self._uid(), hostel_id=hostel_id,
                room_id=room_id, reported_by=supervisor_id,
                category=cat, title=title, description=desc,
                priority=priority,
                status="completed" if i % 3 == 0 else ("in_progress" if i % 3 == 1 else "open"),
                estimated_cost=500.0 + (i * 200),
                actual_cost=450.0 + (i * 180) if i % 3 == 0 else None,
                requires_admin_approval=needs_approval,
                approved_by=admin_id if needs_approval and i % 2 == 0 else None,
            ))
        await self._flush()

    async def create_reviews(self, hostel_id: str, visitor_ids: list[str]) -> None:
        reviews = [
            (4.8, "Excellent hostel!", "Clean rooms, great food, and friendly staff."),
            (4.5, "Very good experience", "Good facilities and nice location."),
            (4.2, "Comfortable stay", "Decent hostel with good amenities."),
            (5.0, "Perfect for students!", "Absolutely love this hostel. Highly recommended!"),
        ]
        for i, (rating, title, content) in enumerate(reviews):
            visitor_id = visitor_ids[i % len(visitor_ids)]
            self.session.add(Review(
                id=self._uid(), visitor_id=visitor_id,
                hostel_id=hostel_id, booking_id=None,
                overall_rating=rating,
                cleanliness_rating=min(5.0, rating + 0.1),
                food_rating=max(3.0, rating - 0.3),
                security_rating=min(5.0, rating + 0.2),
                value_rating=max(3.5, rating - 0.1),
                title=title, content=content,
                is_verified=True, is_published=True,
                admin_reply="Thank you for your feedback!" if i % 2 == 0 else None,
            ))
        await self._flush()

    async def create_subscription(self, hostel_id: str) -> None:
        subscription = Subscription(
            id=self._uid(),
            hostel_id=hostel_id,
            tier="professional",
            price_monthly=2999.0,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() + timedelta(days=305),
            status="active",
            auto_renew=True,
        )
        self.session.add(subscription)
        await self._flush()

    async def create_inquiry(self, hostel_id: str) -> None:
        inquiries = [
            ("Ravi Kumar", "ravi.kumar@gmail.com", "+91-9111111111", "Is there availability for a single room?"),
            ("Preethi S", "preethi.s@gmail.com", "+91-9222222222", "What are the monthly charges including food?"),
        ]
        for name, email, phone, msg in inquiries:
            self.session.add(Inquiry(
                id=self._uid(), hostel_id=hostel_id,
                name=name, email=email, phone=phone, message=msg,
            ))
        await self._flush()

    async def run(self) -> None:
        print("\n" + "="*60)
        print("  🌱  Levitica Nestora — Core Admin Accounts Only")
        print("="*60 + "\n")

        print("👤 Creating 4 core admin users...\n")

        # 1. Super Admin
        await self.create_user(
            "superadmin@leviticanestora.com", "+91-9000000001",
            "Super Admin", UserRole.SUPER_ADMIN,
        )

        # 2. Hostel Admin 1
        await self.create_user(
            "admin1@leviticanestora.com", "+91-9000000100",
            "Hostel Admin 1", UserRole.HOSTEL_ADMIN,
        )

        # 3. Hostel Admin 2
        await self.create_user(
            "admin2@leviticanestora.com", "+91-9000000101",
            "Hostel Admin 2", UserRole.HOSTEL_ADMIN,
        )

        # 4. Supervisor 1
        await self.create_user(
            "supervisor1@leviticanestora.com", "+91-9000000200",
            "Supervisor 1", UserRole.SUPERVISOR,
        )

        # ── Commit ─────────────────────────────────────────────────────
        print("\n💾 Committing users to database...\n")
        await self.session.commit()

        print("="*60)
        print("  ✅  Core Users Seed Complete (0 sample hostels/rooms)!")
        print("="*60)
        print(f"""
  📊 Summary
  ──────────────────────────────────────
  Super Admin  : superadmin@leviticanestora.com
  Admin 1      : admin1@leviticanestora.com
  Admin 2      : admin2@leviticanestora.com
  Supervisor 1 : supervisor1@leviticanestora.com
  
  🔑 Password for all: Test@1234
  ──────────────────────────────────────
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def _run():
    import sys
    clean = "--clean" in sys.argv or "--reset" in sys.argv

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"statement_cache_size": 0},  # Required for Supabase Transaction Pooler (pgbouncer)
    )

    if clean:
        print("\n🗑️  Cleaning existing data (--clean flag)...\n")
        async with engine.begin() as conn:
            tables = [
                "complaint_comments", "notice_reads", "attendance_records",
                "maintenance_requests", "reviews", "inquiries",
                "payment_webhook_events", "payments", "bed_stays",
                "booking_status_history", "students", "bookings",
                "beds", "rooms", "hostel_amenities", "hostel_images",
                "admin_hostel_mappings", "supervisor_hostel_mappings",
                "visitor_favorites", "subscriptions", "complaints",
                "notices", "mess_menu_items", "mess_menus", "hostels",
                "otp_verifications", "refresh_tokens", "users",
            ]
            for table in tables:
                try:
                    await conn.execute(__import__("sqlalchemy").text(f'TRUNCATE TABLE "{table}" CASCADE'))
                    print(f"  ✓ Cleared {table}")
                except Exception as e:
                    try:
                        await conn.execute(__import__("sqlalchemy").text(f'DELETE FROM "{table}"'))
                        print(f"  ✓ Cleared {table} (via DELETE)")
                    except Exception:
                        pass
        print("\n  ✓ Data clearing complete\n")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        seeder = LeviticaNestoraSeeder(session)
        await seeder.run()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())