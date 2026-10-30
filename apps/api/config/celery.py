import sys
import os
from celery import Celery

# Set default Django settings module for 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('mediacompile', include=['content.tasks', 'integrations.tasks'])

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# On Windows, prefork pool is unstable and unsupported by Celery. Enforce solo pool.
if sys.platform == 'win32':
    app.conf.worker_pool = 'solo'
    app.conf.worker_prefetch_multiplier = 1

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

from celery.signals import task_prerun, task_postrun

@task_prerun.connect
def on_task_prerun(*args, **kwargs):
    """Ensure clean connection state and close any stale sockets before task starts."""
    from django.db import close_old_connections
    close_old_connections()

@task_postrun.connect
def on_task_postrun(*args, **kwargs):
    """Release database connection immediately after task finishes to prevent pool exhaustion."""
    from django.db import close_old_connections
    close_old_connections()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
