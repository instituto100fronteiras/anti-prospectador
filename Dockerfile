# Use official lightweight Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including timezone support)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set Timezone
ENV TZ=America/Sao_Paulo

# Copy requirements first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose ports
# 5001: Webhook
# 8501: Dashboard
EXPOSE 5001
EXPOSE 8501

# Grant execution permission to entrypoint
RUN chmod +x entrypoint.sh

# Run
CMD ["./entrypoint.sh"]
