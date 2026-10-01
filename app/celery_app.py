"""
Celery configuration for Levitica Nestora.
Handles background tasks like email sending, payment processing, etc.
"""
from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

# Create Celery app instance
celery_app = Celery(
    'leviticanestora',
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        'app.tasks.email_tasks',
        'app.tasks.payment_tasks',
        'app.tasks.waitlist_tasks',
        'app.tasks.complaint_sla_tasks',
        'app.tasks.booking_tasks',
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        "scan-complaint-sla": {
            "task": "app.tasks.complaint_sla.scan_breaches",
            "schedule": crontab(minute="*/30"),
        },
        "auto-checkout-expired-bookings": {
            "task": "app.tasks.booking_tasks.auto_checkout_expired_bookings_celery",
            "schedule": crontab(minute="*/5"),
        },
    },
)


def get_celery_app():
    """Get Celery app instance."""
    return celery_app
