import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "selfhealthos.settings.dev")

app = Celery("selfhealthos")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:
    """Trivial task used to prove the broker round-trip works."""
    return f"ok from {self.request.id}"
