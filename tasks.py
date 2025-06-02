from celery import Celery
from main import generate_monthly_report

celery_app = Celery('tasks', broker='redis://localhost:6379/0')
celery_app.task(name='generate_monthly_report')(generate_monthly_report)