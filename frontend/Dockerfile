# Recipe for the frontend container (Streamlit UI).
# Built from the project root (see docker-compose.yml).

FROM python:3.14-slim

WORKDIR /app

# The UI only needs Streamlit and requests.
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/ frontend/
COPY .streamlit/ .streamlit/

CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true"]
