from pylibrnp.defaultpackets import *
from pylibrnp.rnppacket import *
# import ..pylibrnp.defaultpackets
# import ..pylibrnp.rnppacket


import socketio
import argparse
import json



sio = socketio.Client(logger=True, engineio_logger=True)

task_json = {
    "task_name": "fc_telemetry",
    "autostart":False,
    "poll_delta": 1000,
    "running": True,
    "logger": True,
    "request_config": {
        "source": 1,
        "destination": 0,
        "destination_service": 2,
        "command_id": 8,
        "command_arg": 0
    },
    "packet_descriptor": {
        "pn": "float",
        "pe": "float",
        "pd": "float",
        "vn": "float",
        "ve": "float",
        "vd": "float",
        "an": "float",
        "ae": "float",
        "ad": "float",
        "roll": "float",
        "pitch": "float",
        "yaw": "float",
        "q0": "float",
        "q1": "float",
        "q2": "float",
        "q3": "float",
        "lat": "float",
        "lng": "float",
        "alt": "int",
        "sat": "uint8_t",
        "ax": "float",
        "ay": "float",
        "az": "float",
        "h_ax": "float",
        "h_ay": "float",
        "h_az": "float",
        "gx": "float",
        "gy": "float",
        "gz": "float",
        "mx": "float",
        "my": "float",
        "mz": "float",
        "baro_temp": "float",
        "baro_press": "float",
        "baro_alt": "float",
        "batt_voltage": "uint16_t",
        "batt_percent": "uint16_t",
        "launch_lat": "float",
        "launch_lng": "float",
        "launch_alt": "int",
        "system_status": "uint32_t",
        "system_time": "uint64_t",
        "rssi": "int16_t",
        "snr": "float"
    }
}

@sio.event
def connect():
    print("I'm connected!")

@sio.event
def connect_error(data):
    print("The connection failed!")

@sio.event
def disconnect():
    print("I'm disconnected!")

@sio.on('runningTasks',namespace='/data_request_handler')
def on_response_handler(data):
    print(data)
 

@sio.on('Error',namespace='/command')
def on_error_handler(data):
    print(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=False, help="backend host", type=str,default = "localhost")
    ap.add_argument("--port", required=False, help="backend port", type=int,default = 1337)
    args = vars(ap.parse_args())

    sio.connect('http://' + args["host"] + ':' + str(args['port']) + '/',namespaces=['/','/telemetry','/data_request_handler','/messages'])

    # input("get")
    # sio.emit('getRunningTasks',namespace='/data_request_handler')
    # input("get")
    sio.emit('newTaskConfig',task_json,namespace='/data_request_handler')
    # input("get")
    # sio.emit('getRunningTasks',namespace='/data_request_handler')
    # input("get")
    # sio.emit('deleteTaskConfig',{'task_name':'fc_telemetry'},namespace='/data_request_handler')
    # input("get")
    # sio.emit('getRunningTasks',namespace='/data_request_handler')


    