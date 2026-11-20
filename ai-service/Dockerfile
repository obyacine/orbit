FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY scripts ./scripts

EXPOSE 8001
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
