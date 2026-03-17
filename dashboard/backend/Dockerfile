FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed (e.g., for psycopg2)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY dashboard/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Need to copy bot root config and src since backend depends on them
# The context of this docker build MUST be the root of the project (All_bot)
COPY . /app/

# Set working directory to project root as expected by main.py
WORKDIR /app

# Run Gunicorn with Uvicorn workers
CMD ["gunicorn", "dashboard.backend.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8043"]
