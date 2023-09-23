# Argument for base image (default: slim)
ARG BASEIMAGE="debian-slim"

## Base image using Debian
FROM python:latest as debian

# Update/upgrade packages
RUN apt-get update && apt-get upgrade -y

## Base image using slim Debian
FROM python:slim as debian-slim

# Update/upgrade packages
RUN apt-get update && apt-get upgrade -y

# Install git
RUN apt-get install git -y

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
COPY ./.git ./.git
COPY ./.gitmodules ./.gitmodules
COPY ./external ./external
COPY ./Logs ./Logs
COPY ./ricardobackend ./ricardobackend
COPY ./main.py ./main.py
COPY ./RicardoBackend.sh ./RicardoBackend.sh

# Initialise and update submodules
RUN git submodule init && git submodule update

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
