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
        --monitor-port $MONITOR_PORT\
&
sleep 5
python3 ricardobackend/websocketforwarder/websocketforwarder.py --sio_host ricardo-backend --sio_port 1337 --ws_host 0.0.0.0 --ws_port 1338
