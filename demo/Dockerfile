FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --upgrade pip==25.0.1 \
    && pip install fastapi==0.115.6 uvicorn[standard]==0.34.0 httpx==0.28.1

COPY app.py ./

EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
