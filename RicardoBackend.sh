#!/bin/bash

# Generate the list of arguments
args=()
# Device arguments
args+=(
    "--device $RICARDO_BACKEND_DEVICE"
    "--baud $RICARDO_BACKEND_BAUD"
)
# Flask arguments
args+=(
    "--flask-host $RICARDO_BACKEND_FLASK_HOST"
    "--flask-port $RICARDO_BACKEND_FLASK_PORT"
)
# Verbose flag
if [[ $RICARDO_BACKEND_VERBOSE == "TRUE" ]]; then
    args+=("--verbose")
fi
# Monitor flag and arguments
if [[ $RICARDO_BACKEND_MONITOR == "TRUE" ]]; then
    args+=("--monitor")
fi
args+=(
    "--monitor-ip $RICARDO_BACKEND_MONITOR_IP"
    "--monitor-port $RICARDO_BACKEND_MONITOR_PORT"
)
# Websockets arguments
args+=(
    "--ws_host $RICARDO_BACKEND_WS_HOST"
    "--ws_port $RICARDO_BACKEND_WS_PORT"
)
# Fake data flag
if [[ $RICARDO_BACKEND_FAKE_DATA == "TRUE" ]]; then
    args+=("--fake_data")
fi
# Convert argument array to string
args_str="${args[@]}"

# Print the arguments
echo "Ricardo Backend arguments:"
for arg in "${args[@]}"
do
   echo $arg
done

# Print start message
echo "Starting the Ricardo Backend"

# Execute the Ricardo Backend main file
python3 main.py $args_str

# Print exit message
echo "Ricardo Backend exited"