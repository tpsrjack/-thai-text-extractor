# ── Thai Text Extractor by KruJack ──
# Docker image for Render deployment
FROM python:3.12-slim

# Install system dependencies for OCR + PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tha \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Tesseract data path
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# Set working directory
WORKDIR /app

# Copy Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY templates/ templates/

# Expose port (Render sets PORT env var to 10000)
EXPOSE 8080

# Run with gunicorn (production WSGI server)
# 1 worker + preload = memory efficient for EasyOCR (~500MB models)
# 300s timeout for large OCR jobs
# Uses $PORT env var (Render sets this to 10000), falls back to 8080
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --preload --timeout 300 --log-level info app:app
