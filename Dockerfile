FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install poetry==2.3.* && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY config/ ./config/
COPY templates/ ./templates/
COPY src/ ./src/

CMD ["python", "-m", "muse.main"]
