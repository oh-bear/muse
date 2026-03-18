FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install poetry==2.3.* && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY config/ ./config/
COPY templates/ ./templates/
COPY src/ ./src/

RUN poetry install --only main --no-interaction --no-ansi

COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
