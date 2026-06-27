FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=django_settings.settings \
    NO_ALBUMENTATIONS_UPDATE=1

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        libpq-dev \
        pkg-config \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements/base.txt backend/requirements/mysql.txt backend/requirements/postgres.txt ./requirements/
RUN pip install --upgrade pip \
    && pip install -r requirements/base.txt -r requirements/mysql.txt -r requirements/postgres.txt \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple

COPY backend/ /app/

COPY docker/backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 10808

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "django_settings.asgi:application", "--host", "0.0.0.0", "--port", "10808", "--workers", "4", "--proxy-headers"]
