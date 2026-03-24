FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY prompts/ prompts/

EXPOSE 8000

CMD ["uvicorn", "flexloop.main:app", "--host", "0.0.0.0", "--port", "8000"]
