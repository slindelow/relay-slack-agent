FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY . .

RUN chmod +x scripts/start_web.sh

EXPOSE 3000

CMD ["bash", "scripts/start_web.sh"]
