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

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first (layer caching) — only pyproject.toml + uv.lock change rarely
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY src ./src
COPY README.md ./

# Install the package itself
RUN uv sync --frozen --no-dev

# Put the project venv on PATH so the `whatsapp` entry-point script resolves at ENTRYPOINT.
ENV PATH="/app/.venv/bin:$PATH"

# API keys passed at runtime via -e flags
ENV OPENAI_API_KEY=""
ENV ELEVENLABS_API_KEY=""

# Default: headless mode. Additional args (--output, --limit, etc.) are appended.
# Interactive TUI: docker run -it IMAGE whatsapp (overrides entrypoint to drop --headless)
ENTRYPOINT ["whatsapp", "--headless"]
CMD []
