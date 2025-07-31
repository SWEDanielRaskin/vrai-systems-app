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

# Expose port
EXPOSE 5000

# Set environment variable
ENV PORT=5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"] 