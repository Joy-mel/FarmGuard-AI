# Use a stable, lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the backend requirements file first to keep builds fast
COPY api/requirements.txt ./api/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r api/requirements.txt

# Copy everything else from your root project into the container
COPY . .

# Expose the port Uvicorn runs on
EXPOSE 8000

# Tell python to look inside the root directory for modules
ENV PYTHONPATH=/app

# Start Uvicorn pointing directly to your api folder setup
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]