FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 8000
# Single worker on purpose: the in-process gauges model one engine replica, and
# KEDA scales by adding pods (replicas), not workers.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
