FROM python:3.11-slim

WORKDIR /app

# Create non-root user (security best practice)
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser appuser

# In a real situation, install dependencies

# Copy application
COPY app.py .

# Set ownership of app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

CMD ["python", "app.py"]