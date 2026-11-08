FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=0
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.4 && groupadd --gid 10001 butler && useradd --uid 10001 --gid butler --no-create-home butler && install -d -m 0700 -o butler -g butler /run/butler-work
COPY pyproject.toml uv.lock /app/
COPY app /app/app
RUN uv sync --frozen --no-dev --no-editable
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
