FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# # compile python from source - avoid unsupported library problems
# RUN apt-get update && \
#     apt-get install -y software-properties-common && \
#     add-apt-repository -y ppa:deadsnakes/ppa && \
#     apt-get update && \
#     apt install -y python3.9

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install PyTorch
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make port 5000 available
EXPOSE 5000

# Command to run the application
CMD ["python3", "app.py"]