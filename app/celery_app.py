import logging
from celery import Celery
from celery.schedules import crontab
from app.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config['log_level'], logging.INFO),
    format='[%(levelname)s][%(asctime)s]: %(message)s'
)
logger = logging.getLogger(__name__)

# Create Celery instance
celery_app = Celery(
    'mini_nightscout',
    broker=config['redis_url'],
    backend=config['redis_url'],
    include=['app.tasks.glucose']
)

# Configure Celery
celery_app.conf.update(
    # Use pickle for serialization (to handle complex objects)
    accept_content=['json', 'pickle'],
    task_serializer='pickle',
    result_serializer='pickle',
    # Set timezone
    timezone='UTC',
    enable_utc=True,
    # Configure task routing
    task_routes={
        'app.tasks.glucose.*': {'queue': 'glucose'}
    }
)

# Configure scheduled tasks
# Set up fetch_glucose_data task to run according to interval in config
fetch_interval = config['glucose_fetch_interval']
celery_app.conf.beat_schedule = {
    'fetch-glucose-data': {
        'task': 'app.tasks.glucose.fetch_glucose_data',
        'schedule': fetch_interval,  # Run every X seconds (default 60)
        'options': {'queue': 'glucose'}
    },
}

logger.info(f"Celery application initialized with broker: {config['redis_url']}")
logger.info(f"Scheduled tasks: fetch_glucose_data every {fetch_interval} seconds")