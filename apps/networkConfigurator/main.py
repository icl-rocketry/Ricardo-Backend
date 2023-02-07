import argparse
import socket
from serialmanager import SerialManager
from socketioConnector import SocketioConnector
from pylibrnp.defaultpackets import SimpleCommandPacket
import pylibrnp.rnppacket as rnppacket
import json
import multiprocessing
import sys
import signal
import time
import os
import networkConfigurator

import cmd2
import sys
from cmd2.argparse_custom import Cmd2ArgumentParser
from cmd2.decorators import with_argparser
from pylibrnp.defaultpackets import *
from pylibrnp.rnppacket import *
import argparse
import time
import enum

import socketio

ap = argparse.ArgumentParser()
ap.add_argument("--backend-host",required = False , help="Ip of backend",type = str)
ap.add_argument("--backend-port",required = False , help="Port of backend",type = int,default = 1337)
ap.add_argument("-d", "--dev", required=False, help="Serial Device", type=str)
ap.add_argument("-b", "--baud", required=False, help="Serial Buad", type=int,default=115200)
ap.add_argument("-c", "--config", required=True, help="Config file", type=str)
ap.add_argument("-v", "--verbose", required=False, help="Config file", action='store_true',default=False)

args = vars(ap.parse_args())

def exitHandler(*args):
    global exit_app
    print('Exiting UdpAdapter')
    print("Killing Processes")
    exit_app = True
    [p.terminate() for p in proclist]
    [p.join() for p in proclist]
    sys.exit(0)


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn',force=True)

    #process arguments
    if args["backend_host"] is not None and args["dev"] is not None:

        print("[ERROR] both backend_host and dev passed!")
        sys.exit(0)
    
    networkConfigurator = networkConfigurator.NetworkConfigurationTool()


    
    exit_app = False
    signal.signal(signal.SIGINT, exitHandler)
    signal.signal(signal.SIGTERM, exitHandler)

    receivePacketQueue = multiprocessing.Queue()
    sendPacketQueue = multiprocessing.Queue()
    proclist = []
    udpRxPortQueueList = []
    #import config
    with open(args['config']) as jsonfile:
        config = json.load(jsonfile)


    if args['dev'] is not None:
        sm = SerialManager(device=args['dev'],
                           sendQ=sendPacketQueue,
                           receiveQ=receivePacketQueue,
                           baud=args['baud'],
                           verbose=args['verbose'])

        proclist.append(multiprocessing.Process(target=sm.run))
    
    elif args['backend_host'] is not None:
        proclist.append(multiprocessing.Process(target=SocketioConnector,
                                                args=(args['backend_host'],
                                                args['backend_port'],
                                                sendPacketQueue,
                                                receivePacketQueue,
                                                args['verbose'],)))

    else:
        print("Error no connection specified!")
        sys.exit(0)

    #spawn processes
    [p.start() for p in proclist]

    prevTime = 0
    while not exit_app:
        if (time.time_ns() - prevTime > 100e6):
            cmd_packet = SimpleCommandPacket(command=8,arg=0) # 8 for telemetry
            cmd_packet.header.source = 1
            cmd_packet.header.destination = 0
            cmd_packet.header.source_service = 2
            cmd_packet.header.destination_service = 2
            # udpTxPort.queue.put({"data":bytes(cmd_packet.serialize())})
            prevTime = time.time_ns()