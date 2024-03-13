# Standard imports
import argparse
import asyncio
import logging
import signal
import sys
import time

# Third-party imports
import socketio
import socketio.exceptions
import websockets

# Set logging paramet
# logger = logging.getLogger('websockets')
# logger.setLevel(logging.DEBUG)
# logger.addHandler(logging.StreamHandler())
# logging.getLogger("asyncio").setLevel(logging.INFO)
# logging.getLogger("asyncio").addHandler(logging.StreamHandler())

# Set time conversion constants
MS_TO_NS = 1e6
NS_TO_MS = 1e-6


class WebsocketForwarder:

    def __init__(
        self,
        sio_host: str = "localhost",
        sio_port: int = 1337,
        ws_host: str = "localhost",
        ws_port: int = 8080,
    ) -> None:
        # Set signal handlers
        signal.signal(signal.SIGINT, self.exitHandler)
        signal.signal(signal.SIGTERM, self.exitHandler)

        # Declare Socket.IO client
        self.sio = socketio.AsyncClient()

        # Declare data queue dictionary (thread-safe through GIL)
        self.data_queue_dict = {}
        self.data_queue_maxsize = -1 #unlimited for now?

        # Set run flag
        self.run = True

        # Declare event loop attribute
        self.eventLoop = None

        # Set Socket.IO URL
        self.sio_url = "http://" + sio_host + ":" + str(sio_port) + "/"

        # Store WebSocket host and port
        self.ws_host = ws_host
        self.ws_port = ws_port

        # Start WebSocket server
        self.start_ws_server = websockets.serve(
            self.send_to_websocket, ws_host, ws_port
        )

        # Register Socket.IO client callbacks
        self.sio.on("connect", self.connect)
        self.sio.on("connect_error", self.connect_error)
        self.sio.on("disconnect", self.disconnect)
        self.sio.on("*", self.forward_telemetry, namespace="/telemetry")
        self.sio.on("*", self.forward_telemetry, namespace="/system_events")

    async def connect(self) -> None:
        # Print connection message
        print("Connected")

    async def connect_error(self, e) -> None:
        # Print connection error
        print(e)

    async def disconnect(self) -> None:
        # Print disconnection message
        print("Disconnected")

    async def forward_telemetry(self, event, data) -> None:

        # Check if the event exists in the data dict or thre is space to add a new key
        if not self.addNewQueue(event):
            return

        # Try to put the data on the event queue
        try:
            self.data_queue_dict[event].put_nowait(data)
        except asyncio.QueueFull:
            # Drop data if the queue is full
            return

    async def send_to_websocket(self, websocket, path) -> None:
        # Print path
        print(path) #TODO use logging library!!

        # Strip prefix from path to get telemetry key
        # TODO: more robust method?
        telemetry_key = path[len("/ws/") :]

        # Check that telemetry key exists in the data queue dictionary
        # Check if the event exists in the data dict or thre is space to add a new key
        if not self.addNewQueue(telemetry_key): # ? we might want to instead send null/NaN rather than just make the queue???
            return

        # Extract data queue
        data_queue = self.data_queue_dict[telemetry_key]

        # Print connection message
        print(telemetry_key + " connected")

        # Loop while run flag is set
        while self.run:
            # Get data from queue
            # TODO: update to ensure that the forwarded data is realtime
            data = await data_queue.get()

            # Send data over WebSocket
            # TODO: set timestamp on the DataRequestHandler?
            # await websocket.send(
            #     f'{{"timestamp": {time.time_ns()*NS_TO_MS}, "data": {data}}}'
            # )
            await websocket.send(
                data
            )

            # Sleep to reduce loop rate
            await asyncio.sleep(0.01)

    async def main(self) -> None:
        # Enter connection loop
        while True:
            try:
                # Connect to the Socket.IO server
                await self.sio.connect(self.sio_url, namespaces=["/telemetry","/system_events"])

                # Break loop
                break
            except socketio.exceptions.ConnectionError:
                # Print connection error message
                print(
                    "[WebsocketForwarder]: Couldn't connect to SIO server, trying again!"
                )

                # Sleep to reduce retry rate
                await asyncio.sleep(1)

        # Wait for the connection to end
        await self.sio.wait()

    def start(self) -> None:
        # Add tasks to event loop
        asyncio.get_event_loop().run_until_complete(self.start_ws_server)
        asyncio.get_event_loop().run_until_complete(self.main())

        # Run event loop
        self.eventLoop = asyncio.get_event_loop().run_forever()

    def exitHandler(self, sig, frame) -> None:
        # Check if event loop exists
        if self.eventLoop is not None:
            # Close event loop
            self.eventLoop.close()

        # Print exit message
        print("\nWebsocketforwarder Exited!")

        # Exit
        sys.exit(0)
    
    def addNewQueue(self,taskname):
        if len(self.data_queue_dict) == self.data_queue_maxsize:
            print("Error number of keys in data dict exceeds max size! " + str(self.data_queue_maxsize))
            return False
        
        if taskname not in self.data_queue_dict.keys():
            # Spawn new queue
            self.data_queue_dict[taskname] = asyncio.Queue(maxsize=2) #contention??

        return True


if __name__ == "__main__":
    # Declare argument parser
    ap = argparse.ArgumentParser()

    # Add arguments
    ap.add_argument(
        "--sio_host",
        required=False,
        help="Socketio Host",
        type=str,
        default="localhost",
    )
    ap.add_argument(
        "--sio_port", required=False, help="Socketio Port", type=int, default=1337
    )
    ap.add_argument(
        "--ws_host",
        required=False,
        help="Websocket Host",
        type=str,
        default="localhost",
    )
    ap.add_argument(
        "--ws_port", required=False, help="Websocket Port", type=int, default=8080
    )

    # Parse arguments
    args = vars(ap.parse_args())

    # Create WebSocket forwarder
    websocketforwarder = WebsocketForwarder(
        sio_host=args["sio_host"],
        sio_port=args["sio_port"],
        ws_host=args["ws_host"],
        ws_port=args["ws_port"],
    )

    # Start WebSocket forwarder
    websocketforwarder.start()
