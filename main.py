import multiprocessing
import argparse
import sys
import time
import signal

from ricardobackend.flaskinterface import flaskinterface
from ricardobackend.serialmanager import serialmanager
from ricardobackend.websocketforwarder import websocketforwarder




# Argument Parsing
ap = argparse.ArgumentParser()
ap.add_argument("-d", "--device", required=False, help="Ricardo Serial Port", type=str)
ap.add_argument("-b", "--baud", required=False, help="Serial Port Baud Rate", type=int,default=115200)
ap.add_argument("--flask-host", required=False, help="flask host", type=str,default="0.0.0.0")
ap.add_argument("--flask-port", required=False, help="flask Port", type=int,default = 1337)
ap.add_argument("-v", "--verbose", required=False, help="Enable Verbose Mode", action='store_true')
ap.add_argument('-mon','--monitor', required=False, help="Enable network monitoring ",action='store_true',default=False)
ap.add_argument('-monip','--monitor-ip', required=False, help="Set network monitoring ip",type=str,default = "127.0.0.1")
ap.add_argument('-monport','--monitor-port', required=False, help="Set network monitoring port",type=int,default = 7000)
ap.add_argument('--ws_host',required=False, help="websocket host", type=str,default = "0.0.0.0")
ap.add_argument('--ws_port',required=False, help="websocket port", type=int,default = 1338)
ap.add_argument('--fake_data',required=False, help="serve fake data",action='store_true',default=False)
ap.add_argument('--no_autoreconnect',required=False, help="Disable serial autoreconnect",action='store_true',default=False)

argsin = vars(ap.parse_args())

proclist = {}

def exitBackend(sig,frame):
    global proclist
    for key in proclist:
        print("Killing: " + key + " Pid: " + str(proclist[key].pid))
        proclist[key].terminate()
        proclist[key].join()

    sys.exit(0)

def startSerialManager(args,sendQueue,receiveQueue_dict):

    serman = serialmanager.SerialManager(device = args["device"],
                                     baud = args["baud"],
                                     autoreconnect= not args['no_autoreconnect'],
                                     UDPMonitor=args['monitor'],
                                     UDPIp=args['monitor_ip'],
                                     UDPPort=args["monitor_port"],
                                     verbose=args['verbose'],
                                     sendQ=sendQueue,
                                     receiveQ_dict=receiveQueue_dict)
    serman.run()

def startWebSocketForwarder(args):
    wsforwarder = websocketforwarder.WebsocketForwarder(sio_host = "127.0.0.1",
                                                        sio_port = args['flask_port'],
                                                        ws_host = args['ws_host'],
                                                        ws_port = args['ws_port'])
    wsforwarder.start()

def startFlaskInterface(args,sendQueue,receiveQueue):
    flaskinterface.startFlaskInterface(flaskhost=args['flask_host'],
                                       flaskport=args['flask_port'],
                                       fake_data=args['fake_data'],
                                       verbose=args['verbose'],
                                       sendQueue=sendQueue,
                                       receiveQueue=receiveQueue)


if __name__ == '__main__':

    signal.signal(signal.SIGINT,exitBackend)
    signal.signal(signal.SIGTERM,exitBackend)

    sendQueue = multiprocessing.Queue()
    receiveQueue_dict = {"flaskinterface":multiprocessing.Queue()}

    if not (argsin['fake_data']):
        if argsin.get('device',None) is None:
            raise Exception("No device passed")
        proclist['serialmanager'] = multiprocessing.Process(target=startSerialManager,args=(argsin,sendQueue,receiveQueue_dict,))
        proclist['serialmanager'].start()

    #start flask interface process
    proclist['flaskinterface'] = multiprocessing.Process(target=startFlaskInterface,args=(argsin,sendQueue,receiveQueue_dict['flaskinterface']))
    proclist['flaskinterface'].start()
    time.sleep(1)

    proclist['websocketforwarder'] = multiprocessing.Process(target=startWebSocketForwarder,args=(argsin,))
    proclist['websocketforwarder'].start()

    while(True):
        pass






 