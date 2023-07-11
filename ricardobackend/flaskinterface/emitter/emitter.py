# Module (with interactive interface)


# MODULES
# System Modules
import time
import eventlet
# User Modules
from .util import parser_csv as parser_csv
from .util import processor as processor

    
# System Variables


#Class implementation to respect the kill signal from flaskinterface
class EmitterClass():
    def __init__(self,socketio,filename:str,loop:bool = False,verbose:bool = False):
        self.data_array = parser_csv.parse_log(filename)
        self.index = 0
        self.loop = loop
        self.sio = socketio
        self.verbose = verbose

    def emit(self):
        if self.index < len(self.data_array):
            item = self.data_array[self.index]
            package = processor.format_package(item["data"])
            if self.verbose:
                print(package)
                print("Emitting package " + str(self.index))
            self.sio.emit("fc_telemetry", package, namespace="/telemetry")
      

            self.index += 1
            if self.loop and self.index == len(self.data_array):
                self.index = 0

            eventlet.sleep(item["interval"]/1000)
        return

        