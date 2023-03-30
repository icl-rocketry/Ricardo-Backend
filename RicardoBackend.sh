#!/bin/bash

# Execute backend, using parameters supplied via environment variables
# TODO: add verbose and monitor flags
python3 main.py \
        --device $DEVICE \
        --baud $BAUD \
        --flask-host $FLASK_HOST \
        --flask-port $FLASK_PORT \
        --monitor-ip $MONITOR_IP \
        --monitor-port $MONITOR_PORT\
        --ws_port $WS_PORT\
        --ws_host $WS_HOST\
        -v

