FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System dependencies. Tesseract is the OCR engine used by src/pdf_loader.py to
# read the scanned catalog; baking it into the image keeps OCR reproducible
# instead of depending on what's installed on the host. The English language
# pack ships with the tesseract-ocr package. Clean apt lists to keep it small.
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

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["python", "-m", "src.main"]
