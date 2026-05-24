# API + pipeline (단일 컨테이너). 프론트는 Vercel 등 정적/Next 호스팅 권장.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py config.py ./
COPY services ./services
COPY data ./data
COPY web/backend ./web/backend

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

RUN mkdir -p web/jobs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --app-dir web/backend --host 0.0.0.0 --port ${PORT}"]
