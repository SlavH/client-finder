FROM python:3.13-slim

# Install system dependencies for browser automation and noVNC
RUN apt-get update && apt-get install -y \
    xvfb \
    fluxbox \
    websockify \
    novnc \
    chromium-browser \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libasound2 \
    zstd \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browser binaries
RUN playwright install chromium && \
    playwright install-deps chromium

WORKDIR /client-finder

# Copy project files
COPY pyproject.toml README.md LEGAL.md ./
COPY config.yaml.example .env.example ./
COPY Me/ ./Me/
COPY mcp/ ./mcp/
COPY opencode/ ./opencode/
COPY client_finder/ ./client_finder/

# Install Python package
RUN pip install -e .

# Create state directories
RUN mkdir -p state/cookies work/ && \
    chmod 700 state/cookies

# Expose noVNC port
EXPOSE 6080

# Environment variables
ENV DISPLAY=:99
ENV NOVNC_HOST=localhost
ENV PYTHONUNBUFFERED=1

# Default command - show help
CMD ["client-finder", "--help"]