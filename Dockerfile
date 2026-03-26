FROM python:3.13-slim

# System dependencies for ADB, Appium, and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g appium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev

# Copy application code
COPY . .

# Install the package itself
RUN poetry install --no-interaction --no-ansi --without dev

# API keys passed at runtime via -e flags
ENV OPENAI_API_KEY=""
ENV ELEVENLABS_API_KEY=""

# Default: headless mode. Additional args (--output, --limit, etc.) are appended.
# Interactive TUI: docker run -it IMAGE whatsapp (overrides entrypoint to drop --headless)
ENTRYPOINT ["whatsapp", "--headless"]
CMD []
