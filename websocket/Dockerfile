# Use Python 3.9
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose WebSocket port
EXPOSE 8080

# Set environment variable
ENV PORT=8080

# Run the WebSocket server
CMD ["python", "websocket_server.py"] 