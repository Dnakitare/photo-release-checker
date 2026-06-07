FROM python:3.11-slim

# dlib needs a C++ toolchain + cmake to build its wheel.
RUN apt-get update && \
    apt-get install -y --no-install-recommends cmake g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Production server. The app factory creates tables on startup; the instance/
# directory (SQLite app DB + audit ledger) should be a mounted volume so data
# and the tamper-evident log persist across container restarts.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "wsgi:app"]
