# Build the frontend in a Node stage, then copy the static bundle into the app image.
FROM node:22-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Tesseract is the OCR engine used by src/pdf_loader.py to read the scanned catalog.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached across code changes.
# psycopg2-binary ships wheels, so no build toolchain is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application. Code is baked into the image rather than bind-mounted
# (see README: the project lives in iCloud Drive, which is unreliable to mount).
COPY src/ ./src/
COPY data/ ./data/
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x ./docker/entrypoint.sh

# Static frontend built in the Node stage, served by the API at the same origin.
COPY --from=frontend /web/dist ./frontend/dist

# Default command is the CLI; the api service (docker-compose) overrides it with
# uvicorn and serves HTTP on this port.
EXPOSE 8000

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["python", "-m", "src.main"]
