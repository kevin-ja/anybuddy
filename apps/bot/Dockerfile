FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# 1) Dependencies (solo las del bot, no las de la API)
COPY apps/bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Bot source code
COPY apps/bot/ ./

CMD ["python", "discord_bot.py"]