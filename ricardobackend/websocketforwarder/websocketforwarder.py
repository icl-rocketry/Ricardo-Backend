import os
os.environ['PYTHONASYNCIODEBUG'] = '1'

import asyncio
import socketio
import websockets
from websockets import exceptions as ws_exceptions
import time
import argparse
import signal
import sys

MS_TO_NS = 1e6
NS_TO_MS = 1e-6

class WebsocketForwarder():
    sio = socketio.AsyncClient()
    data_queue_dict = {} #threadsafe thru gil.. rip

    def __init__(self,sio_host:str="localhost",sio_port:int=1337,ws_host="localhost",ws_port="8080", udpQueue=None):
        signal.signal(signal.SIGINT,self.exitHandler)
        signal.signal(signal.SIGTERM,self.exitHandler)

        self.run = True
        self.eventLoop = None

        self.sio_url = "http://"+sio_host+":"+str(sio_port)+"/"
        self.ws_host = ws_host
        self.ws_port = ws_port
        self.udpQueue = udpQueue
        self.start_ws_server = None
        #register socketio client callbacks
        self.sio.on('connect',self.connect)
        self.sio.on('connect_error',self.connect_error)
        self.sio.on('disconnect',self.disconnect)
        self.sio.on('*',self.forward_telemetry,namespace='/telemetry')

    async def connect(self):
        print('connected')

    async def connect_error(self,e):
        print(e)

    async def disconnect(self):
        print('disconnected')

    async def forward_telemetry(self, event, data):
        print(f"[WebsocketForwarder] Received telemetry event={event}")

        if event not in self.data_queue_dict:
            print(f"[WebsocketForwarder] Creating queue for telemetry key={event}")
            self.data_queue_dict[event] = asyncio.Queue(maxsize=2)

        if self.udpQueue:
            try:
                self.udpQueue.put_nowait(data)
            except Exception as e:
                print(f"[WebsocketForwarder] Failed to put on udpQueue: {e}")

        try:
            self.data_queue_dict[event].put_nowait(data)
        except asyncio.QueueFull:
            print(f"[WebsocketForwarder] Queue for {event} full, dropping sample")
            return
        
    async def send_to_websocket(self, websocket):
        path = websocket.path
        print(f"[WebsocketForwarder] Incoming WS connection on path: {path}")

        if not path.startswith("/ws/"):
            print(f"[WebsocketForwarder] Invalid path, closing: {path}")
            await websocket.close()
            return

        telemetry_key = path[len("/ws/"):]
        print(f"[WebsocketForwarder] Requested telemetry key: {telemetry_key}")

        while telemetry_key not in self.data_queue_dict:
            # print(f"[WebsocketForwarder] Waiting for telemetry_key={telemetry_key} to appear...")
            await asyncio.sleep(0.5)

        data_queue = self.data_queue_dict[telemetry_key]
        print(f"[WebsocketForwarder] {telemetry_key} connected")

        try:
            while self.run:
                data = await data_queue.get()
                await websocket.send(
                    f'{{"timestamp": {time.time_ns() * NS_TO_MS}, "data": {data}}}'
                )
        except ws_exceptions.ConnectionClosed:
            print(f"{telemetry_key} disconnected")

    async def main(self):
        # robust connect with retries and backoff
        await self._connect_with_retry()

        # optionally verify namespace connected
        if "/telemetry" not in self.sio.namespaces:
            # namesapces is populated in python-socketio >= 5
            raise RuntimeError("Connected, but /telemetry namespace not available")

        print("[WebsocketForwarder] Connected and ready. Waiting for events...")
        await self.sio.wait()
      
    async def _connect_with_retry(self):
        attempt = 0
        while True:
            attempt += 1
            try:
                print(f"[WebsocketForwarder] Connecting to {self.sio_url} (attempt {attempt})")
                await self.sio.connect(
                    self.sio_url,
                    namespaces=["/telemetry"],
                    wait=True,
                    wait_timeout=5,  # seconds
                )
                print("[WebsocketForwarder] Connected to Socket.IO server")
                return
            except socketio.exceptions.ConnectionError as e:
                print(f"[WebsocketForwarder] ConnectionError: {e}")
            except asyncio.TimeoutError:
                print("[WebsocketForwarder] Connection timed out")

            if self.max_retries is not None and attempt >= self.max_retries:
                raise RuntimeError(
                    f"[WebsocketForwarder] Failed to connect to {self.sio_url} "
                    f"after {attempt} attempts"
                )

            # exponential backoff with cap
            delay = min(self.base_delay * 2 ** (attempt - 1), 30.0)
            print(f"[WebsocketForwarder] Retrying in {delay:.1f} s...")
            await asyncio.sleep(delay)

    def start(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def setup():
            await websockets.serve(
                self.send_to_websocket,
                self.ws_host,
                self.ws_port
            )

            print(
                f"[WebsocketForwarder] WebSocket server listening on "
                f"{self.ws_host}:{self.ws_port}"
            )

            asyncio.create_task(self.main())

        loop.run_until_complete(setup())
        loop.run_forever()

    def exitHandler(self):
        if self.eventLoop is not None:
            self.eventLoop.close()
        print('\nWebsocketforwarder Exited!')
        sys.exit(0)




if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sio_host", required=False, help="Socketio Host", type=str,default="localhost")
    ap.add_argument("--sio_port", required=False, help="Socketio Port", type=int,default=1337)
    ap.add_argument("--ws_host", required=False, help="Websocket Host", type=str,default="localhost")
    ap.add_argument("--ws_port", required=False, help="Websocket Port", type=int,default=8080)

    args = vars(ap.parse_args())
    
    websocketforwarder = WebsocketForwarder(sio_host=args["sio_host"],sio_port=args["sio_port"],ws_host=args["ws_host"],ws_port=args["ws_port"])
    websocketforwarder.start()
