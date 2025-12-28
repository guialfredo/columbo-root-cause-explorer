FROM python:3.12-slim

WORKDIR /app

# Install dependencies with pinned versions
RUN pip install --no-cache-dir requests==2.31.0

ARG API_ENDPOINT_URL=http://api.old-domain.com/health

ENV API_ENDPOINT=${API_ENDPOINT_URL}

# Copy application code
COPY app.py /app/app.py

CMD ["python", "app.py"]
