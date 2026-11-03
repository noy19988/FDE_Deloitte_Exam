# Recipe for the backend container (FastAPI + ADK agent).
# Built from the project root (see docker-compose.yml).

FROM python:3.14-slim

WORKDIR /app

# Install the libraries first - Docker caches this step,
# so changing our code does not reinstall everything.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Our code and the processed data files.
COPY backend/ backend/
COPY data/processed/ data/processed/

# 0.0.0.0 = accept connections from outside the container.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
