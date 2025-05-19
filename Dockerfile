# Use Python 3.13 slim image as base
FROM python:3.13-slim

# Set working directory
WORKDIR /app

COPY pyproject.toml  .
# Create data directory
RUN mkdir -p data

# Install project dependencies
RUN pip install -e .

# Create a non-root user
RUN useradd -m -u 1000 appuser
RUN chown -R appuser:appuser /app
USER appuser

# Command to run the exporter
ENTRYPOINT ["python", "-m", "mangadex_exporter"]
CMD [] 