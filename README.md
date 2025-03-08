# Live People Counter from CCTV Footage

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- NVIDIA GPU with CUDA support (recommended)

## Quick Start

1. Clone this repository:
   ```bash
   git clone https://github.com/adityojulian/live-people-counter.git
   cd people-counter
   ```

2. Start the application:
   ```bash
   docker-compose up --build
   ```

3. Access the application at: http://localhost:5000

## Running Without GPU

If you don't have a GPU, you need to modify the `docker-compose.yml` file:

1. Remove the `deploy` section:
   ```yaml
   # Remove these lines
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

2. Use the CPU version in the Dockerfile:
   ```dockerfile
   # In Dockerfile, replace the CUDA base image with:
   FROM python:3.9-slim
   
   # And replace the torch installation with CPU version:
   RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
   ```

Note: Performance will be significantly slower without GPU acceleration.

## Data Persistence

The application stores its database in the `./instance` directory which is mounted as a volume. This ensures data persists between container restarts.

## Troubleshooting

### Cannot access the web interface

- Make sure the container is running: `docker-compose ps`
- Check container logs: `docker-compose logs people-counter`
- Ensure port 5000 is not being used by another application

### Slow performance

- Verify that GPU acceleration is working: `docker exec -it people-counter_people-counter_1 nvidia-smi`
- Try lowering the resolution or frame rate in the code

### No camera feed

- Ensure the camera URL is accessible from inside the container
- Some camera streams may require authentication or specific network access
