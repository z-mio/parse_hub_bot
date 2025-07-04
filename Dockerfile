FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /app

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libegl1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

RUN uv venv && uv sync --frozen

CMD ["uv", "run", "bot.py"]
