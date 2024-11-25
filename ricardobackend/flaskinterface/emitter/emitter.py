# Standard imports
import json
import os
import time

# Third-party imports
import eventlet
from flask_socketio import SocketIO
import numpy as np
import pandas as pd
import simplejson

# Default fake telemetry directory
DEFAULT_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class Emitter:
    # TODO add log queue and centralized logging implementation here @artem
    def __init__(self, sio: SocketIO, directory: str = DEFAULT_DIRECTORY, loop: bool = False) -> None:
        
        # Set running flag
        self.running = True
        
        # Store SocketIO client
        self.sio = sio

        # Store telemetry directory
        self.directory = directory

        # Find files
        files = os.listdir(self.directory)

        # Declare name and data arrays
        self.name = []
        self.data = []

        # Iterate through files
        for file in files:
            # Ignore non-CSV files
            if not file.endswith(".csv"):
                continue

            # Extract name
            name = file.rstrip(".csv")

            # Create filepath
            filepath = os.path.join(directory, file)

            # Load data
            try:
                data = pd.read_csv(filepath)
            except:
                continue

            # Store name and data
            self.name.append(name)
            self.data.append(data)
        
        if not self.name or not self.data:
            self.running = False
            #  TODO when logqueue is implemented, change this to raise a critical error instead of an exception @artem
            raise Exception(" No Data found in directory!")
            
        # Extract times
        times = np.concatenate([data["BackendTime"] for data in self.data])

        # Extract unique times
        self.times = np.unique(times)

        # Calculate time deltas
        self.deltas = np.diff(self.times, append=0.0)

        # Set starting time
        self.time = self.times[0]

        # Set loop flag
        self.loop = loop

        # Set index to zero
        self.index = 0

        # Set maximum index
        self.indexMax = len(times) - 1

        

    @staticmethod
    def format(packet: dict, indent: int = 2) -> str:
        # Remove BackendTime field
        packet.pop("BackendTime")

        # Use current time for timestamp
        dataFrame: dict = {"timestamp": time.time_ns() * 1e-6, "data": packet}

        # Return formatted packet
        return json.dumps(dataFrame, indent=indent)

    def emit(self) -> None:
        # Extract current index
        index = self.index

        # Extract current and delta time
        timeCurrent = self.times[index]
        deltaCurrent = self.deltas[index]

        # Iterate through data
        for name, data in zip(self.name, self.data):
            # Extract row corresponding to current time
            row = data[data["BackendTime"] == timeCurrent]

            # Continue loop if non-singular
            if row.shape[0] != 1:
                continue

            # Convert to dictionary
            packet = row.to_dict(orient="records")[0]

            # Format packet
            packet = Emitter.format(packet)

            # Print packet
            self.sio.emit(name, packet, namespace="/telemetry")

        # Update index
        self.index += 1

        # Check for end of time
        if self.index > self.indexMax:
            # Reset index if looping, otherwise end loop
            if self.loop:
                self.index = 0
            else:
                self.running = False

        # Sleep until next time
        # TODO: replace with less dodgy solution
        eventlet.sleep(deltaCurrent / 1000.0)

    def run(self) -> None:
        # Emit until loop terminates
        while self.running:
            self.emit()
