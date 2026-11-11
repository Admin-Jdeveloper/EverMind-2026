import os
import sys
from celery import Celery
from celery.signals import task_prerun, task_postrun

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('mediacompile', include=['content.tasks', 'integrations.tasks'])
app.config_from_object('django.conf:settings', namespace='CELERY')

# On Windows, prefork pool is unstable with Celery; enforce solo pool.
if sys.platform == 'win32':
    app.conf.worker_pool = 'solo'
    app.conf.worker_prefetch_multiplier = 1

app.autodiscover_tasks()


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
