import time

from workers.celery_app import celery_app


@celery_app.task(name="simulate_long_task")
def simulate_long_task(duration: int) -> dict:
    for i in range(duration):
        time.sleep(1)
        print(f"Progress: {i + 1}/{duration}")
    return {"status": "complete", "duration": duration}