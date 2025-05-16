# Future imports
from __future__ import annotations

# Standard imports
import copy
import csv
from datetime import datetime, timezone
import functools
import json
import logging
import logging.handlers
import multiprocessing as mp
import os
from queue import Empty, Full
import signal
import sys
import time
from typing import Any, Callable, Dict, Union, List

# Third-party imports
import eventlet
import jsonschema
import simplejson

# ICLR imports
from pylibrnp import rnppacket
from pylibrnp.defaultpackets import SimpleCommandPacket
from pylibrnp.dynamic_rnp_packet_generator import DynamicRnpPacketGenerator

# Set time conversion constants
S_TO_MS = 1e3
MS_TO_NS = 1e6
NS_TO_MS = 1e-6


class RequestConfig:

    def __init__(
        self,
        source: int,
        destination: int,
        destination_service: int,
        command_id: int,
        command_arg: int,
        source_service: int = 0,
        *args,
        **kwargs,
    ) -> None:
        # TODO: input checking
        # TODO: handle args/kwargs

        # Store parameters
        self.source = source
        self.source_service = source_service
        self.destination = destination
        self.destination_service = destination_service
        self.command_id = command_id
        self.command_arg = command_arg

    @classmethod
    def deserialise(cls, configuration: Dict[str, int]) -> RequestConfig:
        # Return deserialised configuration
        return RequestConfig(**configuration)

    def serialise(self) -> Dict[str, int]:
        # Return serialised configuration
        return {
            "source": self.source,
            "source_service": self.source_service,
            "destination": self.destination,
            "destination_service": self.destination_service,
            "command_id": self.command_id,
            "command_arg": self.command_arg,
        }

    def generate_command(self) -> SimpleCommandPacket:
        # Generate the command packet
        command_packet = SimpleCommandPacket(
            command=self.command_id,
            arg=self.command_arg,
        )

        # Set the source address and service
        command_packet.header.source = self.source
        command_packet.header.source_service = self.source_service

        # Set the destination address and service
        command_packet.header.destination = self.destination
        command_packet.header.destination_service = self.destination_service

        # Set the packet type
        # NOTE: always zero for command packets
        command_packet.header.packet_type = 0

        # Return command packet
        return command_packet


class PacketDescriptor:

    def __init__(self, descriptor: Dict[str, str], *args, **kwargs) -> None:
        # TODO: input checking
        # TODO: handle args/kwargs

        # Store packet descriptor
        self.descriptor = descriptor

        # Generate dynamic packet
        self.packet = DynamicRnpPacketGenerator("anon_packettype", descriptor)

    @classmethod
    def deserialise(cls, config: Dict[str, str]) -> PacketDescriptor:
        # Return packet descriptor
        return PacketDescriptor(config)

    def serialise(self) -> Dict[str, Any]:
        # Return configuration
        return self.descriptor

    def get_packet_class(self):
        # Return packet class
        # TODO: update type hint
        return self.packet.getClass()


class BitfieldDecoder:
    # TODO: upstream to pylibrnp?

    def __init__(
        self,
        variable_name: str,
        bitfield: str,
        flags: List[Dict[str, str]],
        *args,
        **kwargs,
    ) -> None:
        # TODO: input checking
        # TODO: handle args/kwargs

        # Store configuration
        # TODO: update names (and JSON schema)
        self.variable_name = variable_name
        self.bitfield = bitfield
        self.flags = flags

        # Generate lookup table
        self.lookup = {int(flag["id"]): flag["description"] for flag in flags}

    @classmethod
    def deserialise(cls, config: Dict[str, Any]) -> BitfieldDecoder:
        # Return deserialised bitfield decoder
        return BitfieldDecoder(**config)

    def serialise(self) -> Dict[str, Any]:
        # Return serialised bitfield decoder
        return {
            "variable_name": self.variable_name,
            "bitfield": self.bitfield,
            "flags": self.flags,
        }

    def _decode(self, bitfield: int) -> Dict[str, int]:
        # Get binary representation and reverse
        binary = "{0:b}".format(bitfield)[::-1]

        # Decode flags
        flags = {
            value: (int(binary[key]) if key < len(binary) else 0)
            for key, value in self.lookup.items()
        }

        # Return decoded flags
        return flags

    def decode(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Return decoded bitfield
        return {self.variable_name: self._decode(data[self.bitfield])}


class BitfieldDecoderSet:

    def __init__(
        self,
        decoders: List[BitfieldDecoder],
        log: Callable,
        *args,
        **kwargs,
    ) -> None:
        # Store bitfield decoders
        self.decoders = decoders

        # Store logger
        self.log = log

    @classmethod
    def deserialise(
        cls,
        config: List[Dict[str, Any]],
        log: Callable,
    ) -> BitfieldDecoderSet:
        # Deserialise decoders
        decoders = [BitfieldDecoder.deserialise(config_) for config_ in config]

        # Return deserialised bitfield decoders
        return BitfieldDecoderSet(decoders, log)

    def serialise(self) -> List[Dict[str, Any]]:
        # Return serialised decoders
        return [decoder.serialise() for decoder in self.decoders]

    def decode(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Declare dictionary of bitfields
        bitfields = {}

        # Iterate through decoders
        for decoder in self.decoders:
            # Check if the bitfield name already exists in the packet data
            if decoder.variable_name in data.keys():
                # Log error
                self.log(
                    "Bitfield variable name already exists in decoded packet data, skipping...",
                    level=logging.ERROR,
                )

                # Continue to the next bitfield decoder
                continue

            # Check if the bitfield name already exists in the decoded bitfields
            if decoder.variable_name in bitfields.keys():
                # Log error
                self.log(
                    "Bitfield variable name already exists in previously decoded bitfield, skipping...",
                    level=logging.ERROR,
                )

                # Continue to the next bitfield decoder
                continue

            try:
                # Decode bitfield
                bitfield = decoder.decode(data)

                # Update bitfields
                bitfields.update(bitfield)
            except KeyError:
                # Log error
                self.log(
                    "Key not found, skipping...",
                    level=logging.ERROR,
                )

        # Return bitfields
        return bitfields


class DataRequestTask:

    def __init__(
        self,
        task_name: str,
        autostart: bool,
        poll_delta: int,
        running: bool,
        logger: bool,
        receiveOnly: bool,
        groups: List[str],
        request_config: RequestConfig,
        packet_descriptor: PacketDescriptor,
        bitfield_decoders: BitfieldDecoderSet,
        rxCounter: int,
        txCounter: int,
        rxBytes: int,
        txBytes: int,
        connected: bool,
        lastReceivedPacket: str,
        logDirectory: str,
        log: Callable,
        reset: bool = True,
        *args,
        **kwargs,
    ) -> None:
        # TODO: input checking
        # TODO: handle args/kwargs

        # Store configuration
        # TODO: update names (and JSON schema)
        self.task_name = task_name
        self.autostart = autostart
        self.poll_delta = poll_delta
        self.running = running
        self.logger = logger
        self.receiveOnly = receiveOnly
        self.groups = groups
        self.request_config = request_config
        self.packet_descriptor = packet_descriptor
        self.bitfield_decoders = bitfield_decoders
        self.rxCounter = rxCounter
        self.txCounter = txCounter
        self.rxBytes = rxBytes
        self.txBytes = txBytes
        self.connected = connected
        self.lastReceivedPacket = lastReceivedPacket

        # Reset connection variables
        if reset:
            self.rxCounter = 0
            self.txCounter = 0
            self.rxBytes = 0
            self.txBytes = 0
            self.connected = True
            self.lastReceivedPacket = ""

        # Set connection variables
        self.connectionTimeout = 5000
        self.lastReceivedTime = 0
        self.lastDisconnectMessageTime = 0
        self.lastDisconnectMessageDelta = 1000

        # Initialise log file
        filename = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S.%fZ")
            + "_"
            + task_name
            + ".csv"
        )
        self.filePath = os.path.join(logDirectory, filename)
        os.makedirs(os.path.dirname(self.filePath), exist_ok=True)
        self.logfile = open(self.filePath, "a", newline="")

        # Initialise CSV writer
        csvHeader = ["BackendTime"] + packet_descriptor.get_packet_class().packetvars
        self.csv_writer = csv.DictWriter(self.logfile, fieldnames=csvHeader)
        self.csv_writer.writeheader()

        # Set update time
        self.previousUpdateTime = 0

        # Set logger
        self.log = log

    def __del__(self) -> None:
        # Close log file
        self.logfile.close()

    @classmethod
    def deserialise(
        cls,
        config_: Dict[str, Any],
        logDirectory: str,
        log: Callable,
    ) -> DataRequestTask:
        # Make a copy of the configuration
        configuration = copy.deepcopy(config_)

        # Get configuration schema
        schema = cls.load_schema()

        # Validate configuration
        # TODO: how to handle errors? especially since raising an error
        #       does not stop the whole backend, prompting a restart
        jsonschema.validate(instance=configuration, schema=schema)

        # Deserialise objects
        configuration["request_config"] = RequestConfig.deserialise(
            configuration["request_config"]
        )
        configuration["packet_descriptor"] = PacketDescriptor.deserialise(
            configuration["packet_descriptor"]
        )
        configuration["bitfield_decoders"] = BitfieldDecoderSet.deserialise(
            configuration["bitfield_decoders"],
            log,
        )

        # Return deserialised task
        return DataRequestTask(**configuration, logDirectory=logDirectory, log=log)

    def serialise(self) -> Dict[str, Any]:
        # Return serialised configuration
        return {
            "task_name": self.task_name,
            "autostart": self.autostart,
            "poll_delta": self.poll_delta,
            "running": self.running,
            "logger": self.logger,
            "receiveOnly": self.receiveOnly,
            "groups": self.groups,
            "request_config": self.request_config.serialise(),
            "packet_descriptor": self.packet_descriptor.serialise(),
            "bitfield_decoders": self.bitfield_decoders.serialise(),
            "rxCounter": self.rxCounter,
            "txCounter": self.txCounter,
            "rxBytes": self.rxBytes,
            "txBytes": self.txBytes,
            "connected": self.connected,
            "lastReceivedPacket": self.lastReceivedPacket,
        }

    @classmethod
    @functools.lru_cache(1)
    def load_schema(cls) -> Dict[str, Any]:
        # Generate path to schema
        directory = os.path.dirname(os.path.abspath(__file__))
        filename = "DataRequestTaskSchema.json"
        filepath = os.path.join(directory, filename)

        # Load schema
        with open(filepath, "r") as fp:
            schema = json.load(fp)

        # Return schema
        return schema

    def update(self) -> Union[None, SimpleCommandPacket]:
        # Check if task is running
        if not self.running:
            return None

        # Get current time
        currentTime = time.time_ns()

        # Calculate time deltas
        lastReceivedDelta = currentTime - self.lastReceivedTime
        lastDisconnectMessageDelta = currentTime - self.lastDisconnectMessageTime

        # Calculate timeouts
        connectionTimeout = self.connectionTimeout * MS_TO_NS
        disconnectMessageTimeout = self.lastDisconnectMessageDelta * MS_TO_NS

        # Check if the connection has timed out
        if lastReceivedDelta > connectionTimeout:
            # Update the connection flag
            self.connected = False

            # Check if enough time has passed to send a disconnect message
            if lastDisconnectMessageDelta > disconnectMessageTimeout:
                # Send disconnect message
                self.log(f"{self.task_name} disconnected", level=logging.WARNING)

                # Update last disconnect message time
                self.lastDisconnectMessageTime = currentTime

        # Check for receive-only mode
        if self.receiveOnly:
            return None

        # Calculate time since last update
        previousUpdateDelta = currentTime - self.previousUpdateTime

        # Calculate polling rate
        pollDelta = self.poll_delta * MS_TO_NS

        # Check if insufficient time has passed since the previous update
        if previousUpdateDelta < pollDelta:
            return None

        # Generate command packet
        command_packet = self.request_config.generate_command()

        # Update previous update time
        self.previousUpdateTime = currentTime

        # Increment transmission counter
        self.txCounter += 1

        # Increment transmission bytes counter
        # NOTE: packet size is only the payload, not including the header, so need to manually add header size
        self.txBytes += command_packet.header.size + command_packet.size

        # Return command packet
        return command_packet

    def decode(self, bytes: bytearray) -> Union[None, Dict[str, Any]]:
        # Update connection state variables
        self.rxCounter += 1
        self.rxBytes += len(bytes)
        self.lastReceivedTime = time.time_ns()
        self.lastReceivedPacket = bytes.hex()

        # Check if task was previously disconnected
        if not self.connected:
            # Update connection status
            self.connected = True

            # Log reconnection
            self.log(f"{self.task_name} reconnected", level=logging.INFO)

        try:
            # Deserialise packet
            packet = self.packet_descriptor.get_packet_class().from_bytes(bytes)
        except rnppacket.DeserializationError as e:
            # Log failure to deserialise
            self.log(f"Received badly formed packet: {e}", level=logging.ERROR)

            # Return
            return None

        # Extract data from the packet
        data: Dict[str, Any] = packet.getData()

        # Check if logging enabled
        if self.logger:
            # Generate record
            record = {
                "BackendTime": time.time() * S_TO_MS,
                **data,
            }

            # Write record to log file
            self.csv_writer.writerow(record)

        # Decode bitfields
        bitfields = self.bitfield_decoders.decode(data)
        data.update(bitfields)

        # Return packet data
        return data


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
        self.task_container: Dict[str, DataRequestTask] = {}

        # Store Socket.IO instance
        self.sio = sio_instance

        # Store verbose flag
        self.verbose = verbose

        # Set Socket.IO event handlers
        self.sio.on_event(
            "connect",
            self.connect,
            namespace="/data_request_handler",
        )

        self.sio.on_event(
            "getRunningTasks",
            self.on_get_running_tasks,
            namespace="/data_request_handler",
        )
        self.sio.on_event(
            "newTaskConfig",
            self.on_new_task_config,
            namespace="/data_request_handler",
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
        self.load_handler_config()  # load handler config if it exists

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
        running_tasks = [task.serialise() for task in self.task_container.values()]

        # Emit to all clients
        self.sio.emit("runningTasks", running_tasks, namespace="/data_request_handler")

    def on_new_task_config(self, data):
        """Adds a new task to the config to reques new data"""
        # if already exists, delete old task and spin up new one
        task_id = data["task_name"]
        self.task_container[task_id] = DataRequestTask.deserialise(
            data,
            self.logs_dir,
            self.__datarequest_log__,
        )

    def on_delete_task_config(self, data):
        # Get task identifier
        task_id = data["task_name"]

        # Pop task from the handler
        # TODO: confirm that destructor is called
        self.task_container.pop(task_id)

    def on_save_handler_config(self, data):
        # Check for no tasks
        if self.task_container is False:
            # Print log message
            # print("[Data Task Request Handler] No Tasks, Saving empty json")
            self.__datarequest_log__("No Tasks, Saving empty json", level=logging.INFO)

            # Set empty task configuration
            handler_config = {}
        else:
            # Extract task configurations
            handler_config = [task.serialise() for task in self.task_container.values()]

        # Declare empty JSON string
        json_string = ""

        try:
            # Try to set JSON string from task configuration
            json_string = json.dumps(handler_config, indent=1)
        except Exception as e:
            # Log error
            self.__datarequest_log__(
                "Config save error: " + str(e),
                level=logging.ERROR,
            )

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
                        # print("[Data Task Request Handler] Empty Json Config")
                        self.__datarequest_log__(
                            "Empty Json Config",
                            level=logging.ERROR,
                        )

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
                    self.__datarequest_log__(
                        "Error opening config file!",
                        level=logging.ERROR,
                    )

                    # Return
                    return

        except FileNotFoundError as e:
            # Log error
            self.__datarequest_log__("No Config Found! " + str(e), level=logging.ERROR)

            # Return
            return

    def on_clear_tasks(self):
        # Extract task identifiers
        task_ids = self.task_container.keys()

        # Clear tasks
        # TODO: confirm that destructor is called
        [self.task_container.pop(task_id) for task_id in task_ids]

    def mainloop(self):
        # Start run loop
        while self.run:
            # Iterate through tasks
            for task_id, task in self.task_container.items():
                # Generate request packet
                request_packet = task.update()

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
        decodedData = task.decode(data)

        # Check if there is no data to decode
        if decodedData is None:
            # Return
            return

        # create data frame
        dataFrame: dict = {"timestamp": time.time_ns() * NS_TO_MS, "data": decodedData}
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
            {
                "data": packet.serialize().hex(),
                "identifier": self.identifier,
            }
        )

        # Set task identifier
        send_data["identifier"]["task_id"] = task_id

        try:
            # Try to put the packet on the send queue
            self.sendQ.put_nowait(send_data)
        except Full:
            # Print error
            # print("[Data Task Request Handler] Send Queue Full!")
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
                # print("[Data Task Request Handler] dumping")
                self.__datarequest_log__("dumping", level=logging.INFO)

        except Empty:
            # Continue as there are no packets to process
            pass

    def __exitHandler__(self, sig=None, frame=None):
        # Exit all tasks
        # [task.__exit__() for task in self.task_container.values()]

        # Disable run flag
        self.run = False

        # Exit process
        sys.exit(0)

    def __datarequest_log__(self, msg, level=logging.DEBUG):
        message = "[Data Task Request Handler] - " + str(msg)
        self.logger.log(level, message)
        # decode log level to string
        logLevel = logging.getLevelName(level)
        # create system event for log message
        systemEvent = {
            "level": logLevel,
            "name": "Data Task Request Handler",
            "msg": msg,
            "time": time.time_ns() * NS_TO_MS,
            "source": {"application": "Ricardo-Backend", "ip": ""},
        }
        self.sio.emit(
            "new_event", simplejson.dumps(systemEvent), namespace="/system_events"
        )
