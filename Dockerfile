FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/data/bot.sqlite

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY bot ./bot

RUN useradd --system --uid 10001 bot && mkdir /data && chown bot /data
USER bot
VOLUME /data

CMD ["python", "main.py"]
