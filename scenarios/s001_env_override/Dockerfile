FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir requests pyyaml

COPY app.py /app/app.py
COPY config/ /app/config/

CMD ["python", "app.py"]
