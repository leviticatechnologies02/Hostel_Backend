# Levitica Nestora Backend API

FastAPI + PostgreSQL + Redis + Celery — multi-tenant hostel management & booking platform.
Built for **Levitica Technologies — DCM Levitica Nestora**.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.116 + Uvicorn |
| Database | PostgreSQL 14+ via SQLAlchemy 2.x async |
| Auth | JWT (access + httpOnly refresh cookie) |
| Payments | Razorpay (orders + webhook) |
| Email | aiosmtplib (Gmail / Mailtrap) |
| Background | Celery + Redis |
| File Storage | AWS S3 (presigned URLs) |
| Migrations | Alembic |

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (optional — for Celery background tasks)

### 2. Setup

```bash
cd hostel-management-api
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Minimum required in `.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/leviticanestora_dev
SECRET_KEY=your-secret-key-at-least-32-chars

# Email (Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAIL_FROM=your@gmail.com
```

### 4. Create the database

```sql
-- In psql:
CREATE DATABASE leviticanestora_dev;
```

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Seed sample data

```bash
# First run (or reset everything):
python -m scripts.seed_data --clean

# Re-seed without clearing:
python -m scripts.seed_data
```

### 7. Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

- Landing page: http://localhost:8000/
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

---

## Seed Data Summary

Running `python -m scripts.seed_data --clean` creates:

| Entity | Count | Details |
|--------|-------|---------|
| Users | 80 | 1 super admin, 2 admins, 4 supervisors, 10 visitors, **63 students** |
| Students | 63 | All from `Employee_Register.xlsx` (Levitica employees LEV001–LEV128) |
| Hostels | 4 | Hyderabad, Bangalore, Pune, Mumbai |
| Rooms | 28 | Single / Double / Triple / Dormitory |
| Beds | 68 | All available by default |
| Bookings | 73 | Various statuses (checked_in, approved, pending, rejected, cancelled) |
| Mess Menus | 8 | Full 7-day × 4-meal (current + next week) per hostel |
| Notices | 32 | 8 per hostel |
| Complaints | 32 | 8 per hostel with SLA tracking |
| Attendance | ~280 | 14 days × 5 students per hostel |
| Maintenance | 24 | 6 per hostel |
| Reviews | 20 | 5 per hostel |
| Subscriptions | 4 | 1 active per hostel |

---

## Login Credentials

All accounts use password: **`Test@1234`**

| Role | Email | Access |
|------|-------|--------|
| Super Admin | `superadmin@leviticanestora.com` | Full platform |
| Hostel Admin 1 | `admin1@leviticanestora.com` | Hyderabad + Bangalore |
| Hostel Admin 2 | `admin2@leviticanestora.com` | Pune + Mumbai |
| Supervisor 1 | `supervisor1@leviticanestora.com` | Green Valley Boys Hostel |
| Supervisor 2 | `supervisor2@leviticanestora.com` | Pearl Girls Hostel |
| Visitor | `arun.kapoor@gmail.com` | Public booking flow |
| Student (Hemant) | `hemant.pawade.lev044@levitica.in` | Student portal |
| Student (Abhilash) | `abhilash.gurrampally.lev029@levitica.in` | Student portal |

> All 63 student emails follow pattern: `firstname.lastname.LEVXXX@levitica.in`

---

## API Modules (126 routes)

| Module | Routes | Description |
|--------|--------|-------------|
| `auth` | 11 | Register, OTP verify, login, refresh, logout, forgot/reset password |
| `public` | 12 | Hostels, rooms, reviews, cities, inquiries, autocomplete, compare |
| `bookings` | 9 | Initiate, payment, cancel, history, waitlist |
| `visitor` | 9 | Profile, bookings, reviews, favorites |
| `student` | 16 | Profile, bookings, payments, attendance, complaints, notices, mess menu |
| `admin` | 32 | Full hostel operations — rooms, beds, bookings, students, payments, etc. |
| `supervisor` | 12 | Attendance, complaints, maintenance, notices, mess menu |
| `super-admin` | 17 | Hostel CRUD, admin management, subscriptions |
| `webhooks` | 1 | Razorpay payment webhook |

---

## Student Workflow

This describes the end-to-end journey from a new visitor registering to becoming a checked-in student.

### Step 1 — Register & Verify

1. Go to `/register`
2. Fill in name, email, phone, password → submit
3. An OTP is sent to your email
4. Enter the OTP on the verify screen → account created with role `visitor`

**Credentials for testing:** `arun.kapoor@gmail.com` / `Test@1234` (pre-seeded visitor)

---

### Step 2 — Browse & Select a Hostel

1. Go to `/hostels` or use the map view
2. Click a hostel → view rooms, amenities, pricing
3. Click **Book Now** → redirected to `/booking/select?hostel=<slug>`

---

### Step 3 — Select Stay Type & Dates (`/booking/select`)

| Field | Notes |
|-------|-------|
| Booking Mode | **Monthly** (min 1 month) or **Daily** (min 1 night) |
| Check-in | Today or future date |
| Check-out | Monthly: min 1 month after check-in · Daily: min next day |
| Room | Select from available rooms — shows live bed count and estimated total |

Click **Select →** on a room to proceed.

---

### Step 4 — Applicant Details (`/booking/details`)

Three-step form:

**Step 1 — Personal Info**
- Full name, date of birth, gender
- Occupation, institution, current address

**Step 2 — Emergency Contact**
- Contact name, phone (10 digits), relationship
- Guardian name/phone (optional)
- Special requirements (optional)

**Step 3 — Identity & Docs**
- Select ID type (Aadhar / PAN / Driving License / Passport / Voter ID)
- Upload document (JPG, PNG, WEBP, PDF — max 10MB)
  - In dev (no S3 configured): upload is simulated, a mock URL is stored
  - In production: file is uploaded to AWS S3 via presigned URL

Click **Review & Pay →** to proceed.

---

### Step 5 — Review & Pay (`/booking/checkout`)

1. Review booking summary and price breakdown
2. **Advance payment = 25% of total rent** is due now
3. Click **Pay ₹X** → Razorpay checkout modal opens
4. Complete payment using test card:
   - Card: `4111 1111 1111 1111`
   - Expiry: any future date · CVV: any 3 digits
   - OTP: `1234` (Razorpay test mode)
5. On success → backend marks booking as `pending_approval`

---

### Step 6 — Booking Confirmation (`/booking/confirmation`)

- Booking number displayed (e.g. `BK-XXXXXX`)
- Status: **Pending Approval** — waiting for hostel admin to review

---

### Step 7 — Admin Approves Booking

Admin logs in at `/admin` → **Bookings** → finds the pending booking → clicks **Approve** → assigns a bed.

Booking status moves: `pending_approval` → `approved`

For monthly stays (and daily stays longer than 10 nights), approval also creates
the tenant/student record and promotes the account from `visitor` to `student`.

---

### Step 8 — Admin Checks In Student

Admin → **Bookings** → approved booking → clicks **Check In**.

This:
- Activates the assigned bed (`BedStay` becomes `ACTIVE`)
- Booking status → `checked_in`
- The tenant record created at approval remains linked to the active bed

---

### Step 9 — Student Portal (`/student/dashboard`)

Once checked in, the student can access:

| Section | What it shows |
|---------|--------------|
| Dashboard | Room info, bed number, check-in date |
| My Bookings | All booking history |
| Payments | Advance paid, monthly rent dues |
| Attendance | Daily check-in/check-out records |
| Complaints | Submit and track complaints |
| Notices | Hostel announcements |
| Mess Menu | Weekly meal schedule |

---

### Step 10 — Check Out

Admin → **Bookings** → checked-in booking → **Check Out**.

- `BedStay` → `COMPLETED` (bed becomes available again)
- Booking status → `checked_out`

---

### Booking Status Flow

```
DRAFT
  └─► PAYMENT_PENDING   (payment initiated)
        └─► PENDING_APPROVAL  (payment confirmed)
              ├─► APPROVED        (admin approves + assigns bed)
              │     └─► CHECKED_IN   (admin checks in student)
              │           └─► CHECKED_OUT
              └─► REJECTED        (admin rejects)

Any status ──► CANCELLED
```

---

## Adding a Supervisor (Admin Workflow)

1. Log in as Hostel Admin at `/admin`
2. Go to **Supervisors** in the sidebar
3. Click **+ Add Supervisor**
4. Fill in: Full Name, Email, Phone, Password
5. Click **Create Supervisor**

The supervisor account is created with role `supervisor` and assigned to the admin's hostel. They can log in at `/login` and access the supervisor dashboard.

---

```
DRAFT → PAYMENT_PENDING → PENDING_APPROVAL → APPROVED → CHECKED_IN → CHECKED_OUT
                                           ↘ REJECTED
Any status → CANCELLED
```

---

## Multi-Tenancy

- `hostel_admin` sees only their assigned hostel(s)
- `supervisor` sees only their assigned hostel
- `student` sees only their own data
- `super_admin` bypasses all tenancy checks

---

## Email

OTPs and booking confirmations are sent via SMTP.
In dev mode (no SMTP configured), OTPs are printed to the console.

Configure Gmail App Password:
1. Enable 2FA on Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create App Password → use in `SMTP_PASSWORD`

---

## Environment Variables

See `.env.example` for the full list. Key variables:

```env
DATABASE_URL          # PostgreSQL connection string
SECRET_KEY            # JWT signing key (min 32 chars)
SMTP_USER             # Gmail address
SMTP_PASSWORD         # Gmail App Password (16 chars)
RAZORPAY_KEY_ID       # Razorpay test key
RAZORPAY_KEY_SECRET   # Razorpay secret
AWS_ACCESS_KEY_ID     # S3 file uploads (optional)
FRONTEND_URL          # http://localhost:5173
```

| Entity | Count |
|---|---|
| Super Admin | 1 |
| Hostel Admins | 2 |
| Supervisors | 4 |
| Visitors | 10 |
| Students | 20 |
| Hostels | 4 (Hyderabad, Bangalore, Pune, Mumbai) |
| Rooms | 28 (single/double/triple/dormitory) |
| Beds | ~80 |
| Bookings | 30 (all statuses) |
| Mess Menu Items | 224 (7 days × 4 meals × 2 weeks × 4 hostels) |
| Notices | 32 (8 per hostel) |
| Complaints | 32 (8 per hostel) |
| Attendance Records | 280 (14 days × 5 students × 4 hostels) |
| Maintenance Requests | 24 (6 per hostel) |
| Reviews | 20 (5 per hostel) |
| Subscriptions | 4 |
| Inquiries | 12 |

### Login Credentials (all use password: `Test@1234`)

| Role | Email |
|---|---|
| Super Admin | superadmin@leviticanestora.com |
| Hostel Admin 1 | admin1@leviticanestora.com |
| Hostel Admin 2 | admin2@leviticanestora.com |
| Supervisor 1 | supervisor1@leviticanestora.com |
| Supervisor 2 | supervisor2@leviticanestora.com |
| Visitor 1 | arun.kapoor@gmail.com |
| Student 1 | rahul.sharma@student.com |
| Student 2 | priya.patel@student.com |

---

## Project Structure

```
app/
  main.py           — FastAPI app, middleware, routers
  config.py         — Settings from .env
  dependencies.py   — Auth guards, DB session
  core/
    database.py     — SQLAlchemy async engine
    security.py     — JWT, password hashing
    tenancy.py      — Multi-tenant access control
    middleware.py   — Request logging, CORS
  models/           — SQLAlchemy ORM models
  schemas/          — Pydantic v2 request/response schemas
  services/         — Business logic layer
  repositories/     — Database query layer
  api/v1/           — Route handlers
    public/         — Public hostel listing, booking
    auth/           — Register, login, OTP, password reset
    admin/          — Hostel admin operations
    supervisor/     — Supervisor workflows
    student/        — Student self-service
    super_admin/    — Platform management
    webhooks/       — Razorpay webhook
  integrations/
    razorpay.py     — Payment gateway
    email.py        — Email notifications
    s3.py           — File uploads
  tasks/            — Celery async tasks
scripts/
  seed_data.py      — Full seed data (run standalone)
  reset_and_seed.py — Drop + recreate + seed (dev only)
alembic/            — Database migrations
```

---

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

Interactive docs: `http://localhost:8000/docs`

Key routes:
- `GET  /public/hostels` — List hostels with filters
- `GET  /public/hostels/{slug}` — Hostel detail
- `POST /auth/register/visitor` — Register
- `POST /auth/login` — Login → JWT tokens
- `POST /public/bookings` — Create booking
- `GET  /admin/dashboard` — Admin dashboard
- `PATCH /admin/bookings/{id}/approve` — Approve booking
- `GET  /student/profile` — Student profile
