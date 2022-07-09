import socketio
import socket
import random
import struct
import time
import requests
import signal
import sys

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
    print(data)  
    print(type(data))  
    udp_data = struct.pack(">ifffffffffffff", time.monotonic_ns()//1_000_000, random.random(), random.random(), random.random(),random.random(), random.random(), random.random(),random.random(), random.random(), random.random(), (random.random()-0.5) * 10, random.random(), random.random(), random.random())
    sock.sendto(udp_data, (IP, UDP_PORT))


def exithandler(sig=None,frame=None):
    print(requests.post(url=f"https://{URL}/end"))
    sys.exit(0)

if __name__ == "__main__":

    IP = "143.47.241.215"
    URL = "live.imperialrocketry.com"

    UDP_PORT = 2052
    WEBSITE_PORT = 5000

    print(requests.post(url=f"https://{URL}/end"))
    print(requests.post(url=f"https://{URL}/start"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    signal.signal(signal.SIGINT, exithandler)

    

    