FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Install common development utilities that tools might use
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    bash \
    jq \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
# Use the system Python environment for our dependencies
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# First, copy only the dependency definition files
COPY pyproject.toml uv.lock ./

# Install dependencies (this layer is cached until pyproject.toml/uv.lock changes)
RUN uv sync --frozen

# Copy the rest of the project files
COPY . .

# Keep the container running or provide a default interactive shell
CMD ["bash"]
