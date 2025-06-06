FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    curl \
    wget \
    gnupg \
    ca-certificates \
    tor \
    && rm -rf /var/lib/apt/lists/*

# Configure Tor
RUN echo "SocksPort 9050" >> /etc/tor/torrc && \
    echo "DataDirectory /var/lib/tor" >> /etc/tor/torrc && \
    echo "Log notice stdout" >> /etc/tor/torrc

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies and yt-dlp
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp && \
    yt-dlp -U && \
    yt-dlp --version

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production
ENV FLASK_APP=app.py

# Expose the port
EXPOSE 10000

# Start Tor and then the application
CMD service tor start && gunicorn --bind 0.0.0.0:10000 --timeout 600 app:app 