# ── Thai Text Extractor by KruJack (Clipboard-only) ──
# Docker image for Render deployment
FROM python:3.12-slim

# Install system dependencies for OCR only (no PDF/poppler needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-tha \
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

# Expose port
EXPOSE 8080

# Run with gunicorn (single worker for memory efficiency)
# Uses $PORT env var (Render sets this to 10000), falls back to 8080
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120 --log-level info app:app
