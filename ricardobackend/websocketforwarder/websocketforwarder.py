import asyncio
import socketio
import websockets
import time
import argparse
import signal
import sys

MS_TO_NS = 1e6
NS_TO_MS = 1e-6

class WebsocketForwarder():
    sio = socketio.AsyncClient()
    data_queue_dict = {} #threadsafe thru gil.. rip

    def __init__(self,sio_host:str="localhost",sio_port:int=1337,ws_host="localhost",ws_port="8080"):
        signal.signal(signal.SIGINT,self.exitHandler)
        signal.signal(signal.SIGTERM,self.exitHandler)

        self.run = True
        self.eventLoop = None

        self.sio_url = "http://"+sio_host+":"+str(sio_port)+"/"
        self.start_ws_server = websockets.serve(self.send_to_websocket, ws_host, ws_port,ping_timeout = None)
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

    async def forward_telemetry(self,event,data):
        #each time we get a new event which has the prefix telemetry we spawn a new queue in a 
        #threadsafe list 
        if (event not in self.data_queue_dict.keys()):
            self.data_queue_dict[event] = asyncio.Queue(maxsize=2)
    
        # await self.data_queue_dict[event].put(data)

        #if queue is full dont wait to put more data on just ignore
        try:
            self.data_queue_dict[event].put_nowait(data)
        except asyncio.QueueFull:
            return
    
    async def send_to_websocket(self,websocket, path):
        print(path)
        telemetry_key = path[len("/ws/"):] #strip prefix from path to get telemetry key
        
        #try retrieve data_queue
        if (telemetry_key not in self.data_queue_dict.keys()):
            print(telemetry_key + ' not found')
            return

        data_queue = self.data_queue_dict[telemetry_key]
        print(telemetry_key + " connected")

        while self.run:
            #we need to update this to make sure the data being forwarded is realtime...
            data = await data_queue.get()
            # async with asyncio.timeout(timeout=1):
                # await websocket.send(f"{{\"timestamp\": {time.time_ns()*NS_TO_MS}, \"data\": {data}}}") #Todo make this not horrible -> maybe timestap should be set on the dtrh rather than here
            await websocket.send(f"{{\"timestamp\": {time.time_ns()*NS_TO_MS}, \"data\": {data}}}") #Todo make this not horrible -> maybe timestap should be set on the dtrh rather than here
            await asyncio.sleep(0.01)

    async def main(self):
        
        while self.run:
            try:
                await self.sio.connect(self.sio_url, namespaces=["/telemetry"]) 
                break
            except socketio.exceptions.ConnectionError:
                print("[WebsocketForwarder]: Couldnt connect to SIO server, trying again!")
                await asyncio.sleep(1)

        await self.sio.wait()    
      

    def start(self):
        asyncio.get_event_loop().run_until_complete(self.start_ws_server)
        asyncio.get_event_loop().run_until_complete(self.main())
        self.eventLoop = asyncio.get_event_loop().run_forever()

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
