# Standard imports
import argparse
from datetime import datetime, timezone
import logging
import logging.handlers
import multiprocessing
import os
import signal
import sys, traceback
import time

# Internal imports
from ricardobackend.flaskinterface import flaskinterface
from ricardobackend.serialmanager import serialmanager
from ricardobackend.websocketforwarder import websocketforwarder


# Declare argument parser
ap = argparse.ArgumentParser()

# Add serial device arguments
ap.add_argument(
    "-d",
    "--device",
    required=False,
    help="Ricardo Serial Port",
    type=str
)
ap.add_argument(
    "-b",
    "--baud",
    required=False,
    help="Serial Port Baud Rate",
    type=int,
    default=115200,
)
ap.add_argument(
    "--no_autoreconnect",
    required=False,
    help="Disable serial autoreconnect",
    action="store_true",
    default=False,
)

# Add Flask arguments
ap.add_argument(
    "--flask-host",
    required=False,
    help="flask host",
    type=str,
    default="0.0.0.0"
)
ap.add_argument(
    "--flask-port",
    required=False,
    help="flask Port",
    type=int,
    default=1337
)

# Add Websocket arguments
ap.add_argument(
    "--ws_host",
    required=False,
    help="websocket host",
    type=str,
    default="0.0.0.0"
)
ap.add_argument(
    "--ws_port",
    required=False,
    help="websocket port",
    type=int,
    default=1338
)

# Add monitor arguments
ap.add_argument(
    "-mon",
    "--monitor",
    required=False,
    help="Enable network monitoring ",
    action="store_true",
    default=False,
)
ap.add_argument(
    "-monip",
    "--monitor-ip",
    required=False,
    help="Set network monitoring ip",
    type=str,
    default="127.0.0.1",
)
ap.add_argument(
    "-monport",
    "--monitor-port",
    required=False,
    help="Set network monitoring port",
    type=int,
    default=7000,
)

# Add directory arguments
ap.add_argument(
    "--config_dir",
    required=False,
    help="Backend Config location",
    type=str,
    default="Config/",
)
ap.add_argument(
    "--logs_dir",
    required=False,
    help="Backend Logfile location",
    type=str,
    default="Logs/",
)

# Add verbose flag argument
ap.add_argument(
    "-v",
    "--verbose",
    required=False,
    help="Enable Verbose Mode",
    action="store_true"
)

# Add fake data argument
ap.add_argument(
    "--fake_data",
    required=False,
    help="serve fake data",
    action="store_true",
    default=False,
)

# Parse arguments
argsin = vars(ap.parse_args())

# Declare process dictionary
proclist = {}


def exitBackend(sig, frame):
    # Declare global variables
    global proclist
    global logger

    # Get system logger
    logger = logging.getLogger("system")

    # Iterate through process dictionary
    for key in proclist:
        # Check for listener process
        # NOTE: left until last
        if key == "listener":
            continue

        # Print kill message
        print("Killing: " + key + " Pid: " + str(proclist[key].pid))

        # Kill process
        proclist[key].terminate()
        proclist[key].kill()
        proclist[key].join()
        proclist[key].close()

    # Print kill message
    print("Killing: listener" + " Pid: " + str(proclist["listener"].pid))

    # Kill listener process
    proclist["listener"].terminate()
    proclist["listener"].kill()
    proclist["listener"].join()
    proclist["listener"].close()

    # Exit
    sys.exit(0)


def startSerialManager(args, sendQueue, receiveQueue, logQueue):
    # Declare serial manager
    serman = serialmanager.SerialManager(
        device=args["device"],
        baud=args["baud"],
        autoreconnect=not args["no_autoreconnect"],
        UDPMonitor=args["monitor"],
        UDPIp=args["monitor_ip"],
        UDPPort=args["monitor_port"],
        verbose=args["verbose"],
        sendQ=sendQueue,
        receiveQ=receiveQueue,
        logQ=logQueue,
    )

    # Start serial manager
    serman.run()


def startWebSocketForwarder(args, logQueue):
    # Declare websocket forwarder
    wsforwarder = websocketforwarder.WebsocketForwarder(
        sio_host="127.0.0.1",
        sio_port=args["flask_port"],
        ws_host=args["ws_host"],
        ws_port=args["ws_port"],
        logQ=logQueue,
    )

    # Run websocket forwarder
    wsforwarder.start()


def startFlaskInterface(args, sendQueue, receiveQueue, logQueue):
    # Declare Flask interface
    flaskiface = flaskinterface.FlaskInterface(
        flaskhost=args["flask_host"],
        flaskport=args["flask_port"],
        fake_data=args["fake_data"],
        verbose=args["verbose"],
        sendQueue=sendQueue,
        receiveQueue=receiveQueue,
        logQ=logQueue,
        config_dir=args["config_dir"],
        logs_dir=args["logs_dir"],
    )

    # Run Flask interface
    flaskiface.run()


def listener_configurer(args):
    # Get system logger
    logger = logging.getLogger("system")

    # Set logger format
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Declare logging file name
    filename = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S.%fZ") + ".log"

    # Declare system logs directory
    path = os.path.join(args["logs_dir"], "SystemLogs")

    # Ensure directory exists
    os.makedirs(path, exist_ok=True)

    # Set logger filepath
    file_path = os.path.join(path, filename)

    # Add file handler
    file_handler = logging.FileHandler(file_path, "a")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Add stream handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def listener_process(args, queue, configurer):
    # Configure the listener
    configurer(args)

    # Enter infinite loop
    while True:
        try:
            # Get record from the queue
            record = queue.get()

            # Break the loop for None record
            if record is None:
                break

            # Get system logger
            logger = logging.getLogger("system")

            # Call logger
            logger.handle(record)
        except Exception:
            # Print error message
            print("Error:", file=sys.stderr)

            # Print traceback
            traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    # Set signal handlers
    signal.signal(signal.SIGINT, exitBackend)
    signal.signal(signal.SIGTERM, exitBackend)

    # Declare log queue
    logQueue = multiprocessing.Queue(-1)  # TODO idk - chnage to some reasonable limit

    # Add listener to the process dictionary
    proclist["listener"] = multiprocessing.Process(
        target=listener_process, args=(argsin, logQueue, listener_configurer)
    )

    # Start listener
    proclist["listener"].start()

    # Declare send and receive queues
    sendQueue = multiprocessing.Queue()
    receiveQueue = multiprocessing.Queue()

    # Check for the fake data flag
    if not argsin["fake_data"]:
        # Raise error if no device provided
        if argsin.get("device", None) is None:
            raise Exception("No device passed")
        
        # Add serial manager to the process dictionary
        proclist["serialmanager"] = multiprocessing.Process(
            target=startSerialManager, args=(argsin, sendQueue, receiveQueue, logQueue)
        )

        # Start serial manager
        proclist["serialmanager"].start()

    # Add Flask interface to the process dictionary
    proclist["flaskinterface"] = multiprocessing.Process(
        target=startFlaskInterface, args=(argsin, sendQueue, receiveQueue, logQueue)
    )

    # Start Flask interface
    proclist["flaskinterface"].start()

    # Sleep
    time.sleep(1)

    # Add websocket forwarder to the process dictionary
    proclist["websocketforwarder"] = multiprocessing.Process(
        target=startWebSocketForwarder, args=(argsin, logQueue)
    )

    # Start websocket forwarder
    proclist["websocketforwarder"].start()
