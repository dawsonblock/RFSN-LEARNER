FROM python:3.12-slim

# Install common dev tools
RUN apt-get update && apt-get install -y \
    git \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
WORKDIR /workspace

# Default command
CMD ["python", "--version"]
