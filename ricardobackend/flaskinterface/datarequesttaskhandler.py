# Standard imports
import copy
import csv
from datetime import datetime, timezone
import json
import multiprocessing as mp
import os
from queue import Full, Empty
import signal
import sys
import time
from typing import Union
import logging
import logging.handlers

# Third-party imports
import eventlet
import simplejson

# ICLR imports
from pylibrnp import rnppacket
from pylibrnp import defaultpackets
from pylibrnp import dynamic_rnp_packet_generator as drpg
from pylibrnp import bitfield_decoder

# Set time conversion constants
MS_TO_NS = 1e6


class DataRequestTask:
    def __init__(self, jsonconfig: dict, logs_dir: str, __datarequest_log__) -> None:
        # Declare task configuration
        self.config = {}

        # Declare incoming data packet class type
        self.packet_class = None

        # Declare list of bitfield decoders to decode system status strings
        self.bitfield_decoder_list = []

        # Update task configuration
        self.updateConfig(jsonconfig)

        # Set connection timeout duration (default: 5000 ms)
        self.connectionTimeout = 5000

        # Initialise last received time
        self.lastReceivedTime = 0
        
        # last disconnect message time 
        self.lastDisconnectMessageTime = 0
        
        # broadcast disconnect message every second
        self.lastDisconnectMesssageDelta = 1000 # 1 second
        
        # Set file name
        # TODO: centralise datetime format string?
        self.fileName = (
            logs_dir
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S.%fZ")
            + "_"
            + self.config["task_name"]
            + ".csv"
        )

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.fileName), exist_ok=True)

        # Open log file
        self.logfile = open(self.fileName, "a", newline="")

        # Generate log file headers
        logfile_header = ["BackendTime"] + self.packet_class().packetvars

        # Create log file writer
        self.csv_writer = csv.DictWriter(self.logfile, fieldnames=logfile_header)

        # Write headers to log file
        self.csv_writer.writeheader()

        # Initialise previous update time
        self.prevUpdateTime = 0

        self.__datarequest_log__ = __datarequest_log__

    def updateConfig(self, jsonconfig: dict) -> None:
        # Store a deep copy of the provided task configuration
        self.config = copy.deepcopy(jsonconfig)

        # Reset connection variables
        self.config["rxCounter"] = 0
        self.config["rxBytes"] = 0
        self.config["txCounter"] = 0
        self.config["txBytes"] = 0
        self.config["connected"] = True
        self.config["lastReceivedPacket"] = ""

        # Generate and store dynamic packet type
        self.packet_class = drpg.DynamicRnpPacketGenerator(
            "anon_packettype", self.config["packet_descriptor"]
        ).getClass()

        # Store a deep copy of the bitfield decoders
        self.bitfield_decoder_list = copy.deepcopy(
            jsonconfig.get("bitfield_decoders", [])
        )

        # Iterate through the bitfield decoders
        for decoder in self.bitfield_decoder_list:
            try:
                # Generate bitfield decoder
                decoder["decoder"] = bitfield_decoder.BitfieldDecoder(decoder["flags"])
            except KeyError:
                # Print error message
                #print("[Data Task Request Handler] Bad Config, ignoring entry" + decoder)
                self.__datarequest_log__("Bad Config, ignoring entry" + decoder, level=logging.ERROR)

                # Continue to next bitfield decoder
                continue

    def requestUpdate(self) -> Union[None, defaultpackets.SimpleCommandPacket]:
        # Check if task is running
        # TODO: refactor
        if self.config["running"]:
            # Check if the connection has timed out
            if time.time_ns() - self.lastReceivedTime > (
                self.connectionTimeout * MS_TO_NS
            ):
                # Update the connection flag
                self.config["connected"] = False
                
                # check if enough time has passed to send a disconnect message
                if time.time_ns() - self.lastDisconnectMessageTime > ( self.lastDisconnectMesssageDelta * MS_TO_NS ):
                    # send disconnect message
                    self.__datarequest_log__(self.config["task_name"] + " Disconnected!", level=logging.WARNING)
                    
                    # update last disconnect message time
                    self.lastDisconnectMessageTime = time.time_ns()
                    

            # Check for receive-only mode
            if self.config.get("receiveOnly", False):
                # Return
                return None

            # Check if enough time has passed since the previous update
            if time.time_ns() - self.prevUpdateTime > (
                self.config["poll_delta"] * MS_TO_NS
            ):
                # Check that a request config has been provided
                requestConfig = self.config.get("request_config", None)
                if requestConfig is None:
                    # Print error message
                    #print("[Data Task Request Handler] Error No Request Config")
                    self.__datarequest_log__("No Request Config", level=logging.ERROR)

                    # Return
                    return None

                # Generate the command packet
                command_packet = defaultpackets.SimpleCommandPacket(
                    command=requestConfig["command_id"],
                    arg=requestConfig["command_arg"],
                )

                # Set the source and service
                command_packet.header.source = requestConfig["source"]
                command_packet.header.source_service = requestConfig.get(
                    "source_service", 0
                )

                # Set the destination and service
                command_packet.header.destination = requestConfig["destination"]
                command_packet.header.destination_service = requestConfig[
                    "destination_service"
                ]

                # Set the packet type
                # NOTE: always zero for command packets
                command_packet.header.packet_type = 0

                # Update previous update time
                self.prevUpdateTime = time.time_ns()

                # Increment transmission counter
                self.config["txCounter"] += 1

                # Increment transmission bytes counter
                # NOTE: packet size is only the payload, not including the header, so need to manually add header size
                self.config["txBytes"] += command_packet.header.size + command_packet.size

                # Return command packet
                return command_packet

        # Return
        return None

    def decodeData(self, data) -> Union[None, dict]:
        # Update connection state variables
        self.config["rxCounter"] += 1
        self.config["rxBytes"] += len(data)
        self.lastReceivedTime = time.time_ns()
        self.config["lastReceivedPacket"] = data.hex()
        # check if task was previously disconnected
        if (self.config["connected"] == False):
            # task has been reconnected
            self.config["connected"] = True
            self.__datarequest_log__(self.config["task_name"] + " Reconnected!", level=logging.INFO)

        try:
            # Deserialise packet
            deserialized_packet = self.packet_class.from_bytes(data)
        except rnppacket.DeserializationError as e:
            # Print error message
            #print("[Data Task Request Handler] received badly formed packet: " + str(e))
            self.__datarequest_log__("Received badly formed packet: " + str(e), level=logging.ERROR)


            # Return
            return None

        # Check if the logging is enabled
        if self.config["logger"]:
            # Generate the record
            data_row = {
                "BackendTime": time.time() * 1000,
                **deserialized_packet.getData(),
            }

            # Write the record to the log file
            self.csv_writer.writerow(data_row)

        # Extract data from the packet
        # TODO: check repeated deserialisation from before
        packetData = deserialized_packet.getData()

        # Iterate through the bitfield decoders
        for decoder in self.bitfield_decoder_list:
            # Get the bitfield decoder variable name
            variableName = decoder.get("variable_name", None)

            # Check if the variable exists in the packet data
            if variableName is None:
                # Continue to the next decoder
                continue

            # Check if the bitfield name already exists in the packet data
            if variableName in packetData.keys():
                # Print error message
                # print(
                #     "[Data Task Request Handler] bitfield variable name already exists in decoded packet data, skipping..."
                # )
                self.__datarequest_log__("Bitfield variable name already exists in decoded packet data, skipping...", level=logging.ERROR)

                # Continue to the next bitfield decoder
                continue

            try:
                # Decode the bitfield
                packetData[variableName] = decoder["decoder"].decode(
                    int(packetData[decoder["bitfield"]])
                )
            except KeyError:
                # Print error message
                #print("[Data Task Request Handler] key not found, skipping...")
                self.__datarequest_log__("Key not found, skipping...", level=logging.ERROR)

                # Continue to the next bitfield decoder
                continue

        # Return the packet data
        return packetData

    def __exit__(self, *args, **kwargs) -> None:
        # Close the log file
        self.logfile.close()


class DataRequestTaskHandler:

    def __init__(
        self,
        sio_instance,
        config_dir: str,
        logs_dir: str,
        sendQ: Union[None, mp.Queue] = None,
        receiveQ: Union[None, mp.Queue] = None,
        logQ: Union[None, mp.Queue] = None,
        prefix: str = "flaskinterface",
        verbose: bool = False,
    ):
        # Set signal handlers
        signal.signal(signal.SIGINT, self.__exitHandler__)
        signal.signal(signal.SIGTERM, self.__exitHandler__)

        # Raise exception if the send and/or receive queue do not exist
        if sendQ is None or receiveQ is None:
            raise Exception(
                "[Data Task Request Handler] No send queue or receive queue provided"
            )

        # Store send and receive queues
        self.sendQ: mp.Queue = sendQ
        self.receiveQ: mp.Queue = receiveQ

        # Set identifier
        self.identifier = {"prefix": prefix, "process_id": "DTRH"}

        # Set configuration filepath
        self.config_filename = config_dir + "DataRequestTaskConfig.json"

        # Set logging directory
        self.logs_dir = logs_dir

        # Declare task container
        self.task_container = {}  # {task_name:task_object}

        # Store Socket.IO instance
        self.sio = sio_instance

        # Store verbose flag
        self.verbose = verbose

        # Set Socket.IO event handlers
        self.sio.on_event(
            'connect',
            self.connect,
            namespace='/data_request_handler',
        )
        
        self.sio.on_event(
            "getRunningTasks",
            self.on_get_running_tasks,
            namespace="/data_request_handler",
        )
        self.sio.on_event(
            "newTaskConfig",
            self.on_new_task_config, 
            namespace="/data_request_handler"
        )
        self.sio.on_event(
            "deleteTaskConfig",
            self.on_delete_task_config,
            namespace="/data_request_handler",
        )
        self.sio.on_event(
            "saveHandlerConfig",
            self.on_save_handler_config,
            namespace="/data_request_handler",
        )
        self.sio.on_event(
            "clearTasks", 
            self.on_clear_tasks, 
            namespace="/data_request_handler",
        )


        # Set run flag
        self.run = True
        self.load_handler_config() #load handler config if it exists

        # Set logging
        self.logQ: mp.Queue = logQ
        queue_handler = logging.handlers.QueueHandler(self.logQ)
        self.logger = logging.getLogger("system")
        self.logger.addHandler(queue_handler)
        self.logger.setLevel(logging.INFO)


    def connect(self):
        pass

    def on_get_running_tasks(self):
        """Returns the current running tasks within the data request task handler as a json"""
        # Concatenate all task configurations
        running_tasks = [task.config for task in self.task_container.values()]

        # Emit to all clients
        self.sio.emit("runningTasks", running_tasks, namespace="/data_request_handler")

    def on_new_task_config(self, data):
        """Adds a new task to the config to reques new data"""
        # if already exists, delete old task and spin up new one
        task_id = data["task_name"]
        self.task_container[task_id] = DataRequestTask(data, self.logs_dir, self.__datarequest_log__)

    def on_delete_task_config(self, data):
        # Get task identifier
        task_id = data["task_name"]

        # Pop task from the handler and call its destructor
        self.task_container.pop(task_id).__exit__()

    def on_save_handler_config(self, data):
        # Check for no tasks
        if self.task_container is False:
            # Print log message
            #print("[Data Task Request Handler] No Tasks, Saving empty json")
            self.__datarequest_log__("No Tasks, Saving empty json", level=logging.INFO)

            # Set empty task configuration
            handler_config = {}
        else:
            # Extract task configurations
            handler_config = [task.config for task in self.task_container.values()]

        # Declare empty JSON string
        json_string = ""

        try:
            # Try to set JSON string from task configuration
            json_string = json.dumps(handler_config, indent=1)
        except Exception as e:
            # Print error message
            #print("[Data Task Request Handler] config save error: " + str(e))
            self.__datarequest_log__("Config save error: " + str(e), level=logging.ERROR)

            # Return
            return

        # Open configuration file
        with open(self.config_filename, "w", encoding="utf-8") as file:
            # Save task configurations
            file.write(json_string)

    def load_handler_config(self):
        try:
            # Open configuration file
            with open(self.config_filename, "r", encoding="utf-8") as file:
                try:
                    # Load configuration file
                    handler_config = json.load(file)

                    # Check for empty configuration file
                    if not handler_config:
                        # Print error message
                        #print("[Data Task Request Handler] Empty Json Config")
                        self.__datarequest_log__("Empty Json Config", level=logging.ERROR)


                        # Return
                        return

                    # Iterate through tasks in configuration file
                    for config in handler_config:
                        # Check if task should autostart
                        if config.get("autostart", 0) is True:
                            config["running"] = True
                        else:
                            config["running"] = False

                        # Generate task
                        self.on_new_task_config(config)

                except json.JSONDecodeError:
                    # Print error message
                    print("[Data Task Request Handler] Error opening config file!")
                    self.__datarequest_log__("Error opening config file!", level=logging.ERROR)

                    # Return
                    return

        except FileNotFoundError as e:
            # Print exception
            #print(e)
            

            # Print error message
            #print("No Config Found!")
            self.__datarequest_log__("No Config Found! " + str(e), level=logging.ERROR)

            # Return
            return

    def on_clear_tasks(self):
        # Extract task identifiers
        task_ids = self.task_container.keys()

        # Call destructor on all tasks
        [self.task_container.pop(task_id).__exit__() for task_id in task_ids]

    def mainloop(self):
        # Start run loop
        while self.run:
            # Iterate through tasks
            for task_id, task in self.task_container.items():
                # Generate request packet
                request_packet = task.requestUpdate()

                # Check that the request packet was generated
                if request_packet is not None:
                    # Send request packet
                    self.__sendPacketFunction__(request_packet, task_id)

            # Check for received packets
            self.__checkReceiveQueue__()

            # Sleep (1 ms) to reduce polling rate
            self.sio.sleep(0.001)

    def publish_new_data(self, data, task_id):
        # Extract task
        task = self.task_container[task_id]

        # Decode data
        decodedData = task.decodeData(data)

        # Check if there is no data to decode
        if decodedData is None:
            # Return
            return

        #create data frame
        dataFrame:dict = {"timestamp":time.time_ns()*1e-6,
                          "data":decodedData}
        # Emit packet on Socket.IO
        # NOTE: simplejson used to dump json as string so that NaNs are converted to null
        # TODO: some kinda of task metadata on telemetry channel too? or maybe on the dtrh channel
        self.sio.emit(
            task_id,
            simplejson.dumps(dataFrame, ignore_nan=True),
            namespace="/telemetry",
        )

    def __sendPacketFunction__(self, packet, task_id):
        # Generate send data with deepcopy
        # NOTE: deepcopy used to prevent reference to self.identifier
        send_data = copy.deepcopy(
            {"data": packet.serialize().hex(), "identifier": self.identifier}
        )

        # Set task identifier
        send_data["identifier"]["task_id"] = task_id

        try:
            # Try to put the packet on the send queue
            self.sendQ.put_nowait(send_data)
        except Full:
            # Print error
            #print("[Data Task Request Handler] Send Queue Full!")
            self.__datarequest_log__("Send Queue Full!", level=logging.ERROR)

    def __checkReceiveQueue__(self):
        try:
            # Get packet from the receive queue
            item = self.receiveQ.get_nowait()

            # Extract task identifier
            identifier = item["identifier"]
            task_id = identifier["task_id"]

            # Check if task exists
            if task_id in self.task_container.keys():
                # Extract response data
                responseData: bytes = item["data"]

                # Publish response data
                self.publish_new_data(responseData, task_id)
            else:
                # Dump packet as task no longer active
                #print("[Data Task Request Handler] dumping")
                self.__datarequest_log__("dumping", level=logging.INFO)


        except Empty:
            # Continue as there are no packets to process
            pass

    def __exitHandler__(self, sig=None, frame=None):
        # Exit all tasks
        [task.__exit__() for task in self.task_container.values()]

        # Disable run flag
        self.run = False

        # Exit process
        sys.exit(0)

    def __datarequest_log__(self, msg, level=logging.DEBUG):
        message = '[Data Task Request Handler] - ' + str(msg)
        self.logger.log(level, message)
        #decode log level to string
        logLevel = logging.getLevelName(level)
        #create system event for log message
        systemEvent = {
                "level":logLevel,
                "name":"Data Task Request Handler", 
                "msg": msg, 
                "time":time.time_ns()*(1e-6),
                "souce":{
                    "application": "Ricardo-Backend",
                    "ip":""
                    }
            }
        self.sio.emit("new_event",simplejson.dumps(systemEvent),namespace="/system_events")
        
