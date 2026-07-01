FROM python:3.11-slim

# Install system deps for pytesseract + OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Back4app exposes port 80 by default
EXPOSE 80

# Start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
