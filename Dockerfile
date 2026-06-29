FROM python:3.14-slim
WORKDIR /app

# Copies the CRM specific requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CRITICAL FIX: Using a completely different port (8000) so they don't clash
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
