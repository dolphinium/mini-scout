"""
Celery application configuration for scheduled tasks.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_config

# Get configuration
config = get_config()

# Create Celery instance
celery_app = Celery(
    'mini_nightscout',
    broker=config["redis_url"],
    backend=config["redis_url"],
    include=['app.tasks.glucose']
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Beat schedule settings
    beat_schedule={
        'fetch-glucose-data': {
            'task': 'app.tasks.glucose.fetch_glucose_data',
            'schedule': config["fetch_interval"],  # Run every X seconds (default: 60)
            'options': {
                'expires': config["fetch_interval"] * 2  # Task expires after twice the interval
            }
        },
    }
)


# Optional startup/shutdown hooks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup any additional periodic tasks."""
    pass


@celery_app.task(bind=True)
def debug_task(self):
    """Task for debugging the Celery worker."""
    print(f'Request: {self.request!r}')