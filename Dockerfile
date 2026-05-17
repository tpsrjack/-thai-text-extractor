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
# 2 workers = balanced for 512MB RAM, 300s timeout for large OCR jobs
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "300", "--log-level", "info", "app:app"]
