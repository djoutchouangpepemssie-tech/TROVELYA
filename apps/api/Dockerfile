# TROVÉLYA API image (Railway): one image for the web process and the arq worker.
FROM python:3.12-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8000
RUN useradd --system --uid 10001 --home /app trovelya
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY alembic.ini ./
COPY src ./src
USER trovelya
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn --factory trovelya.main:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
