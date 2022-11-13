import asyncio
import socketio
import websockets
import time
import random

sio = socketio.AsyncClient()

MS_TO_NS = 1e6
NS_TO_MS = 1e-6

@sio.event
async def connect():
    print('connected')


@sio.event
async def connect_error(e):
    print(e)


@sio.event
async def disconnect():
    print('disconnected')


@sio.on("*", namespace="/telemetry")
async def forward_telemetry(event,data):
    #each time we get a new event which has the prefix telemetry we spawn a new queue in a 
    #threadsafe list 
    if (event not in data_queue_dict.keys()):
        data_queue_dict[event] = asyncio.Queue()

    await data_queue_dict[event].put(data)
    

async def send_to_grafana(websocket, path):
    print(path)
    telemetry_key = path[len("/ws/"):] #strip prefix from path to get telemetry key
    
    #try retrieve data_queue
    if (telemetry_key not in data_queue_dict.keys()):
        print(telemetry_key + ' not found')
        return

    data_queue = data_queue_dict[telemetry_key]
    print(telemetry_key + " connected")

    while True:
        data = await data_queue.get()
        await websocket.send(f"{{\"timestamp\": {time.time_ns()*NS_TO_MS}, \"data\": {data}}}") #Todo make this not horrible
        await asyncio.sleep(0.05)


async def main():
    await sio.connect('http://localhost:1337/', namespaces=["/telemetry"]) #Todo make the port a variable
    await sio.wait()

data_queue_dict = {}
# data_queue = asyncio.Queue()

start_server = websockets.serve(send_to_grafana, 'localhost', 8080)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_until_complete(main())
asyncio.get_event_loop().run_forever()
