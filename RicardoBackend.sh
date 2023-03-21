#!/bin/bash

# Execute backend, using parameters supplied via environment variables
# TODO: add verbose and monitor flags
python3 RicardoBackend.py \
        --device $DEVICE \
        --baud $BAUD \
        --flask-host $FLASK_HOST \
        --flask-port $FLASK_PORT \
        --redis-host $REDIS_HOST \
        --redis-port $REDIS_PORT \
        --monitor-ip $MONITOR_IP \
        --monitor-port $MONITOR_PORT