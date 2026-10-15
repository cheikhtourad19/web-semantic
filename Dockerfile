ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --disable-pip-version-check -r requirements.txt \
    && useradd --create-home --uid 10001 django \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R django:django /app

COPY --chown=django:django . .

USER django
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/web/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

