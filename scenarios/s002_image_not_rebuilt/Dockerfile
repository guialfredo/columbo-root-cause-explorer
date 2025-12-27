FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir requests

# Build argument that will be baked into the image
ARG API_ENDPOINT_URL=http://api.old-domain.com/health

# Convert build arg to environment variable
# This value is FROZEN at build time!
ENV API_ENDPOINT=${API_ENDPOINT_URL}

# Copy application code
COPY app.py /app/app.py

CMD ["python", "app.py"]
