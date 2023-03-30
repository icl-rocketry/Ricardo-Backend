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

# Copy Python requirements file to allow for caching of the pip3 install command
COPY ./requirements.txt ./requirements.txt

# Install Python requirements
RUN pip3 install -r ./requirements.txt

# Copy backend files
COPY . .

# Initialise and update submodules
RUN git submodule init && git submodule update

# Make the backend script executable
RUN chmod +x ./RicardoBackend.sh

# Set default values for environment variables
# TODO: set default device
ENV DEVICE=/dev/null
ENV BAUD=115200
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=1337
ENV MONITOR_IP=127.0.0.1
ENV MONITOR_PORT=7000
ENV WS_PORT=1338
ENV WS_HOST=0.0.0.0

# Run backend script
ENTRYPOINT [ "bash", "RicardoBackend.sh" ]