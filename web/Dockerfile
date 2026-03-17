# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# We copy shared first, then web, to potentially leverage Docker cache better
COPY ./shared /app/shared
COPY ./web /app/web

# Expose the port the app runs on (read from env var, default to 8000)
# This is informational, the actual mapping happens in docker-compose.yml
ARG WEB_APP_PORT=8000
EXPOSE ${WEB_APP_PORT}

# Command to run the application using uvicorn via the Python script
# web/main.py reads the host/port from settings loaded from .env
CMD ["python", "-m", "web.main"]

# Old command:
# CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "${WEB_APP_PORT:-8000}", "--reload"] 