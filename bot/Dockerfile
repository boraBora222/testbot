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
# We copy shared first, then bot, to potentially leverage Docker cache better
COPY ./shared /app/shared
COPY ./bot /app/bot

# Command to run the application
# We assume the main bot script will be in /app/bot/main.py
# You might need to adjust this based on your actual entrypoint file
CMD ["python", "-m", "bot.main"] 