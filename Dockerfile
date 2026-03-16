FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install poetry==1.8.* && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-interaction --no-ansi

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY config/ ./config/
COPY src/ ./src/

CMD ["python", "-m", "muse.main"]
