import asyncio
import socketio
import websockets
import time
import random

sio = socketio.AsyncClient()

@sio.event
async def connect():
    print('connected')


@sio.event
async def connect_error(e):
    print(e)


@sio.event
async def disconnect():
    print('disconnected')


@sio.on("telemetry", namespace="/telemetry")
async def telemetry(data):
    await data_queue.put(data)
    

async def send_to_grafana(websocket, path):
    while True:
        data = await data_queue.get()
        await websocket.send(f"{{\"timestamp\": {time.time()}, \"data\": {data}}}") #Todo make this not horrible
        await asyncio.sleep(0.1)


async def main():
    await sio.connect('http://localhost:3001', namespaces=["/telemetry"]) #Todo make the port a variable
    await sio.wait()


data_queue = asyncio.Queue()

start_server = websockets.serve(send_to_grafana, 'localhost', 8080)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_until_complete(main())
asyncio.get_event_loop().run_forever()
