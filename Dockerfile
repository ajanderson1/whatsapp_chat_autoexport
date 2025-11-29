# WhatsApp Chat Auto Export - Docker Container
# Multi-stage build for optimized image size

# ============================================================================
# Stage 1: Builder - Use Poetry to export dependencies
# ============================================================================
FROM python:3.13-slim AS builder

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

# Set working directory
WORKDIR /app

# Copy poetry files
COPY pyproject.toml poetry.lock ./

# Export dependencies to requirements.txt (excludes dev dependencies)
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# ============================================================================
# Stage 2: Runtime - Install with pip (no Poetry in final image)
# ============================================================================
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Node.js and npm (for Appium)
    curl \
    gnupg \
    # Android SDK tools (adb)
    android-tools-adb \
    # Build tools for Python packages (needed for some pip packages)
    build-essential \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x (required for Appium)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Appium globally
RUN npm install -g appium@2.11.5

# Set working directory
WORKDIR /app

# Copy requirements.txt from builder stage
COPY --from=builder /app/requirements.txt .

# Install Python dependencies with pip (no Poetry)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package itself with pip (registers entry points properly)
RUN pip install --no-cache-dir -e .

# Create output directories
RUN mkdir -p /output /downloads

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/output
ENV DOWNLOADS_DIR=/downloads

# Expose ADB port (for wireless debugging info only)
EXPOSE 5555

# Entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden)
CMD ["--help"]
