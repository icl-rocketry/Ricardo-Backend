# Standard imports
import multiprocessing as mp
from queue import Full, Empty
import signal
import sys
import time
from typing import Callable, Dict, Union

# Third-party imports
from cobs import cobs
import serial
from serial import SerialException
import socket

# ICLR imports
from pylibrnp.rnppacket import DeserializationError, RnpHeader


class SerialManager:

    def __init__(
        self,
        device: str,
        baud: int = 115200,
        autoreconnect: bool = True,
        waittime: float = 0.3,
        sendQ: Union[None, mp.Queue] = None,
        receiveQ: Union[None, mp.Queue] = None,
        verbose: bool = False,
        UDPMonitor: bool = False,
        UDPIp: str = "127.0.0.1",
        UDPPort: int = 7000,
    ) -> None:
        # Set signal handlers
        signal.signal(signal.SIGINT, self.exitHandler)
        signal.signal(signal.SIGTERM, self.exitHandler)

        # Store serial device parameters
        self.device = device
        self.baud = baud
        self.waittime = waittime

        # Set parameters for autoreconnection
        self.autoreconnect = autoreconnect

        # Declare previous send time and delta
        self.prevSendTime = 0
        self.sendDelta = 1e4

        # Store verbose flag
        self.verbose = verbose

        # Set packet record timeout (default: 2 minutes)
        self.packetRecordTimeout = 2 * 60

        # Set message queue size
        self.messageQueueSize = 5000

        # Declare receive buffer
        self.receiveBuffer = []

        # Declare packet record
        # TODO: update type (dict -> {uid:identifier:dict})
        self.packetRecord = {}

        # Declare counter
        self.counter = 0

        # Set receive queue timeout (default: 10 minutes)
        self.receivedQueueTimeout = 10 * 60

        # Raise exception if the send and/or receive queue do not exist
        if sendQ is None or receiveQ is None:
            raise Exception(
                "[Serial-Manager] - Error, no sendqueue or receivequeue passed, exiting"
            )

        # Store send and receive queues
        self.sendQ = sendQ
        self.receiveQ = receiveQ

        # Store UDP monitor
        self.UDPMonitor = UDPMonitor

        # Setup UDP monitor
        if UDPMonitor:
            self.UDPIp = UDPIp
            self.UDPPort = UDPPort

        # Declare local packet handler callbacks
        self.localPacketHandlerCallbacks: Dict[int, Callable[[bytes], None]] = {}

        # Register default message packet callback
        self.registerLocalPacketHandlerCallback(100, self.__decodeMessagePacket__)

    def run(self) -> None:
        # Open socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as self.sock:
            # Try to connect
            self.__auto_connect__()

            # Enter run loop
            while True:
                try:
                    # Check send queue
                    self.__checkSendQueue__()

                    # Read packets
                    self.__readPacket__()

                    # Clean packet record
                    self.__cleanupPacketRecord__()

                except (OSError, serial.SerialException):
                    # Disconnect serial device
                    self.__disconnect__()

                    # Attempt to reconnect
                    self.__auto_connect__()

    def exitHandler(self, sig, frame) -> None:
        # Log exit
        self.__sm_log__("Serial Manager Exited")

        # Disconnect from serial device
        self.__disconnect__()

        # System exit
        sys.exit(0)

    def __auto_connect__(self) -> None:
        # Enter connection loop
        while True:
            try:
                # Attempt to connect
                self.__connect__()

                # Log successful connection
                self.__sm_log__(f"Device {self.device} Connected")

                # Break loop as connection successful
                break
            except (OSError, serial.SerialException):
                # Check reconnection flag
                if self.autoreconnect:
                    # Log attempt to reconnect
                    self.__sm_log__(f"Device {self.device} Disconnected, retrying...")

                    # Sleep to reduce re-try rate
                    time.sleep(1)

                    # Continue reconnection loop
                    continue
                else:
                    # Log exit
                    self.__sm_log__(
                        f"Device {self.device} Disconnected, killing serial manager. Bye bye!"
                    )

                    # Exit
                    self.exitHandler(None, None)

    def __disconnect__(self):
        try:
            # Close serial connection
            self.ser.close()
        except AttributeError:
            # No action
            pass

    def __connect__(self) -> None:
        # Create serial port
        self.ser = serial.Serial(port=None, baudrate=self.baud, timeout=self.waittime)

        # Set serial port path
        self.ser.port = self.device

        # Set serial parameters
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.parity = serial.PARITY_NONE
        self.ser.bytesize = serial.EIGHTBITS

        # Set RTS/DTR lines low
        self.ser.rts = False
        self.ser.dtr = False

        # Open serial port
        self.ser.open()

        # Set RTS/DTR lines high
        self.ser.rts = True
        self.ser.dtr = True

        # Reset ESP32 by pulsing RTS line HIGH for 5 milliseconds
        self.ser.rts = False
        time.sleep(0.005)
        self.ser.rts = True

    def __readPacket__(self) -> None:
        # Loop while data exists in the serial buffer
        while self.ser.in_waiting > 0:
            # Read the first byte in the serial buffer
            incoming = self.ser.read(1)

            # Print incoming byte
            if self.verbose:
                try:
                    print(incoming.decode("UTF-8"), end="")
                except:
                    print(str(incoming), end="")

            # TODO: clarify execution flow

            # Check if the incoming byte is zeros
            if incoming == (0x00).to_bytes(1, "little"):
                # Discard empty frame
                if len(self.receiveBuffer) == 0:
                    break

                # Try to decode the bytes in the receive buffer
                try:
                    # Decode bytes in receive buffer
                    decodedData = cobs.decode(bytearray(self.receiveBuffer))

                    # Processed decoded data
                    self.__processReceivedPacket__(decodedData)

                    # Send decoded packet to UDP
                    self.__sendToUDP__(decodedData)
                except cobs.DecodeError as e:
                    # Print error if decode fails
                    self.__sm_log__(
                        "Decode Error, the following data could not be decoded..."
                    )
                    print(e)
                    print(self.receiveBuffer)

                # Empty receive buffer
                self.receiveBuffer = []
            else:
                # Append byte to receive buffer
                self.receiveBuffer += incoming

    def __processReceivedPacket__(self, data: bytes) -> None:
        # Set received packet flag
        self.received_packet = True

        # Try to deserialise the packet
        try:
            # Decode packet header
            header = RnpHeader.from_bytes(data)
        except DeserializationError:
            # Log deserialisation error
            self.__sm_log__("Deserialisation Error")
            self.__sm_log__(str(data))
            return

        # Check for packet length consistency
        if len(data) != (RnpHeader.size + header.packet_len):
            # Log packet length discrepancy
            self.__sm_log__(
                "Length Mismatch expected:"
                + str((RnpHeader.size + header.packet_len))
                + " Received: "
                + str(len(data))
            )
            self.__sm_log__(data.hex())
            return

        # Extract UID from packet header
        uid = header.uid

        # Check if the UID is in the packet record
        if uid in self.packetRecord:
            # Get client ID from the packet record and remove the corresponding entry
            identifier: str = self.packetRecord.pop(uid)[0]

            # Try to put the packet on the receive queue
            try:
                sendData = {"identifier": identifier, "type": "response", "data": data}
                self.receiveQ.put_nowait(sendData)
            except Full:
                # Log full receive queue and dump the packet
                self.__sm_log__("Receive queue full, dumping packet!")
                return
        else:
            # Check for packets addressed to the local packet handler
            if (uid == 0) and (header.destination_service == 0):
                # Get local packet handler callback (if it exists)
                callback = self.localPacketHandlerCallbacks.get(
                    header.packet_type, lambda x: None
                )

                # Call local packet handler callback
                callback(data)

                return

            # Log unknown packet received and dump the packet
            # TODO: log the packet itself?
            self.__sm_log__("Unknown packet recieved")
            print(header)
            return

    def __sendPacket__(self, data: bytes, identifier: dict) -> None:
        # Decode packet header
        header = RnpHeader.from_bytes(data)

        # Generate packet UID
        uid = self.__generateUID__()

        # Set packet UID
        header.uid = uid

        # Re-serialise the packet header
        serialized_header = header.serialize()

        # Create packet byte array
        modifieddata = bytearray(data)

        # Update header in packet byte array
        modifieddata[: len(serialized_header)] = serialized_header

        # Update packet record
        self.packetRecord[uid] = [
            identifier,
            time.time(),
        ]

        # Send packet byte array to the UDP monitor
        self.__sendToUDP__(modifieddata)  # send data to udp monitor

        # Encode packet
        encoded = bytearray(cobs.encode(modifieddata))

        # Add packet end marker
        encoded += (0x00).to_bytes(1, "little")  # add end packet marker

        # Write packet to the serial connection
        # TODO: check serial port is free?
        self.ser.write(encoded)

    def __checkSendQueue__(self) -> None:
        # Check if time since last send exceeds the send delta
        if time.time_ns() - self.prevSendTime > self.sendDelta:
            # Process the send queue
            self.__processSendQueue__()

            # Update previous send time
            # TODO: clarify repeat in __processSendQueue__
            self.prevSendTime = time.time_ns()

    def __sm_log__(self, msg) -> None:
        # Print log message
        # TODO: replace with better logger?
        print("[Serial Manager] - " + str(msg))

    def __processSendQueue__(self) -> None:
        # Try to send data waiting in key
        try:
            # Get packet from send queue
            item = self.sendQ.get_nowait()

            # Send packet
            self.__sendPacket__(bytes.fromhex(item["data"]), item["identifier"])

            # Update previous send time
            # TODO: clarify repeat in __checkSendQueue__
            self.prevSendTime = time.time_ns()
        except Empty:
            # Return on empty send queue
            return

    def __generateUID__(self) -> int:
        # Increment the counter, ensuring it remains in the range [1 65535]:
        # - UIDs are unsigned 16-bit integers
        # - UID 0 is reserved for local forwarding
        self.counter = (self.counter % 65535) + 1

        # Return counter value
        return self.counter

    def __cleanupPacketRecord__(self) -> None:
        # Calculate packet expiry time
        expiry_time = time.time() - self.packetRecordTimeout

        # Iterate through the packet record, using list to force Python to copy the items
        for key, value in list(self.packetRecord.items()):
            # Remove entry from the packet record if it has expired
            if value[1] < expiry_time:
                self.packetRecord.pop(key)

    def __sendToUDP__(self, data: bytes) -> None:
        # Send packet to UDP monitor
        if self.UDPMonitor:
            self.sock.sendto(data, (self.UDPIp, self.UDPPort))

    def registerLocalPacketHandlerCallback(self, packet_type: int, callback):
        # Update callback
        # NOTE: any existing callbacks will be overrided
        self.localPacketHandlerCallbacks[packet_type] = callback

    def __decodeMessagePacket__(self, data: bytes) -> None:
        # Extract packet header
        header = RnpHeader.from_bytes(data)

        # Extract packet payload
        packet_body = data[RnpHeader.size :]

        # Decode packet payload
        try:
            message = packet_body.decode("UTF-8")
        except:
            message = str(packet_body)

        # Log packet payload
        if self.verbose:
            self.__sm_log__("Message: " + message)

        # Generate packet payload dictionary
        json_message = {
            "header": vars(header),
            "message": message,
            "type": "logmessage",
        }

        # Try to put the decoded packet on the receive queue
        try:
            self.receiveQ.put_nowait(json_message)
        except Full:
            # Log full receive queue
            self.__sm_log__("Receive Queue full, skipping message")
