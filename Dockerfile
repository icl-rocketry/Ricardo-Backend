# Base on default Python image
FROM python:latest

# Update/upgrade packages
RUN apt-get update && apt-get upgrade -y

# Ensure python3 and pip3 are installed
RUN apt-get install python3 python3-pip -y

# Create backend directory
RUN mkdir /ricardo-backend

# Move to backend directory
WORKDIR /ricardo-backend

# Copy backend files
COPY . .

# Make the backend script executable
RUN chmod +x ./RicardoBackend.sh

# Initialise and update submodules
RUN git submodule init && git submodule update

# Install Python requirements
RUN pip3 install -r ./Install/python_requirements.txt

# Set default values for environment variables
# TODO: set default device
ENV DEVICE=/dev/null
ENV BAUD=115200
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=1337
ENV REDIS_HOST=localhost
ENV REDIS_PORT=6379
ENV MONITOR_IP=127.0.0.1
ENV MONITOR_PORT=7000

# Run backend script
ENTRYPOINT [ "bash", "RicardoBackend.sh" ]