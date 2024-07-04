# Argument for base image (default: slim)
ARG BASEIMAGE="debian-slim"

## Base image using Debian
FROM python:3.10 AS debian

# Update/upgrade packages
RUN apt-get update && apt-get upgrade -y

## Base image using slim Debian
FROM python:3.10-slim AS debian-slim

# Update/upgrade packages
RUN apt-get update && apt-get upgrade -y

## Ricardo-Backend image
FROM $BASEIMAGE

# Create backend directory
RUN mkdir /ricardo-backend

# Move to backend directory
WORKDIR /ricardo-backend

# Copy Python requirements file to allow for caching of the pip3 install command
COPY ./requirements.txt ./requirements.txt

# Install Python requirements
RUN pip3 install -r ./requirements.txt

# Copy backend files
COPY ./external/pylibrnp ./external/pylibrnp
COPY ./Logs ./Logs
COPY ./ricardobackend ./ricardobackend
COPY ./main.py ./main.py
COPY ./RicardoBackend.sh ./RicardoBackend.sh

# Make the backend script executable
RUN chmod +x ./RicardoBackend.sh

# Set default values for environment variables
# TODO: set default device
ENV RICARDO_BACKEND_DEVICE=/dev/null
ENV RICARDO_BACKEND_BAUD=115200
ENV RICARDO_BACKEND_FLASK_HOST=0.0.0.0
ENV RICARDO_BACKEND_FLASK_PORT=1337
ENV RICARDO_BACKEND_MONITOR=FALSE
ENV RICARDO_BACKEND_MONITOR_IP=127.0.0.1
ENV RICARDO_BACKEND_MONITOR_PORT=7000
ENV RICARDO_BACKEND_WS_PORT=1338
ENV RICARDO_BACKEND_WS_HOST=0.0.0.0
ENV RICARDO_BACKEND_FAKE_DATA=FALSE

# Run backend script
ENTRYPOINT [ "bash", "RicardoBackend.sh" ]
