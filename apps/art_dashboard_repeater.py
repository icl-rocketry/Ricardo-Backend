import socketio
import json
import socket
import random
import struct
import time
import requests
import signal
import sys

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sio = socketio.Client(logger=False, engineio_logger=False)

sio.connect('http://localhost:1337/',namespaces=['/','/telemetry','/command'])

@sio.event
def connect():
    print("I'm connected!")

@sio.event
def connect_error(data):
    print("The connection failed!")

@sio.event
def disconnect():
    print("I'm disconnected!")

@sio.on('response')
def on_message(data):
    print(data)

@sio.on('package')
def on_message(data):
    print(data)

@sio.on('telemetry',namespace='/telemetry')
def on_message(data):
    data = json.loads(data)
    print(data)  
    print(type(data))  
    # time roll pitch yaw gx gy gz ax ay az mx my mz lat lng alt temp press lux
    udp_data = struct.pack(">iffffffffffffffffff", 
                            data["system_time"], 
                            data["roll"], 
                            data["pitch"], 
                            data["yaw"],
                            data["gx"],
                            data["gy"], 
                            data["gz"],
                            data["ax"], 
                            data["ay"], 
                            data["az"], 
                            data["mx"], 
                            data["my"], 
                            data["mz"], 
                           data["lat"],
                           data["lng"],
                           data["alt"],
                           data["baro_temp"],
                           data["baro_press"],
                           data["rssi"])
    sock.sendto(udp_data, (IP, UDP_PORT))

def exithandler(sig=None,frame=None):
    print(requests.post(url=f"https://{URL}/end"))
    # print(requests.post(url=f"http://{URL}/end"))

    sys.exit(0)

if __name__ == "__main__":

    IP = "143.47.241.215"
    URL = "live.imperialrocketry.com"
    # IP = "127.0.0.1"
    # URL = "localhost:8080"

    UDP_PORT = 2052
    WEBSITE_PORT = 5000

    print(requests.post(url=f"https://{URL}/end"))
    print(requests.post(url=f"https://{URL}/start"))
    # print(requests.post(url=f"http://{URL}/end"))
    # print(requests.post(url=f"http://{URL}/start"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    signal.signal(signal.SIGINT, exithandler)

