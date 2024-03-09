import multiprocessing
import argparse
import sys
import time
import signal
import logging
import logging.handlers
import os
from datetime import datetime

from ricardobackend.flaskinterface import flaskinterface
from ricardobackend.serialmanager import serialmanager
from ricardobackend.websocketforwarder import websocketforwarder




# Argument Parsing
ap = argparse.ArgumentParser()

ap.add_argument("-d", "--device", required=False, help="Ricardo Serial Port", type=str)
ap.add_argument("-b", "--baud", required=False, help="Serial Port Baud Rate", type=int,default=115200)
ap.add_argument('--no_autoreconnect',required=False, help="Disable serial autoreconnect",action='store_true',default=False)

ap.add_argument("--flask-host", required=False, help="flask host", type=str,default="0.0.0.0")
ap.add_argument("--flask-port", required=False, help="flask Port", type=int,default = 1337)

ap.add_argument('--ws_host',required=False, help="websocket host", type=str,default = "0.0.0.0")
ap.add_argument('--ws_port',required=False, help="websocket port", type=int,default = 1338)

ap.add_argument('-mon','--monitor', required=False, help="Enable network monitoring ",action='store_true',default=False)
ap.add_argument('-monip','--monitor-ip', required=False, help="Set network monitoring ip",type=str,default = "127.0.0.1")
ap.add_argument('-monport','--monitor-port', required=False, help="Set network monitoring port",type=int,default = 7000)

ap.add_argument('--config_dir',required=False, help="Backend Config location", type=str,default = "Config/")
ap.add_argument('--logs_dir',required=False, help="Backend Logfile location", type=str,default = "Logs/")

ap.add_argument("-v", "--verbose", required=False, help="Enable Verbose Mode", action='store_true')
ap.add_argument('--fake_data',required=False, help="serve fake data",action='store_true',default=False)


argsin = vars(ap.parse_args())

proclist = {}

def exitBackend(sig,frame):
    global proclist
    global logger
    logger = logging.getLogger("system")
    print("level set to: " + str(logger.getEffectiveLevel()))
    for key in proclist:
        if key == 'listener':
            continue        #leave killing listener to the very end
        else:
            print("Killing: " + key + " Pid: " + str(proclist[key].pid))
            proclist[key].terminate()
            proclist[key].kill()
            proclist[key].join()
            proclist[key].close()

    print("Killing: listener" + " Pid: " + str(proclist["listener"].pid))
    proclist["listener"].terminate()
    proclist["listener"].kill()
    proclist["listener"].join()
    proclist["listener"].close()    

    sys.exit(0)


def startSerialManager(args,sendQueue,receiveQueue,logQueue):

    serman = serialmanager.SerialManager(device = args["device"],
                                     baud = args["baud"],
                                     autoreconnect= not args['no_autoreconnect'],
                                     UDPMonitor=args['monitor'],
                                     UDPIp=args['monitor_ip'],
                                     UDPPort=args["monitor_port"],
                                     verbose=args['verbose'],
                                     sendQ=sendQueue,
                                     receiveQ=receiveQueue,
                                     logQ=logQueue)
    serman.run()

def startWebSocketForwarder(args):
    wsforwarder = websocketforwarder.WebsocketForwarder(sio_host = "127.0.0.1",
                                                        sio_port = args['flask_port'],
                                                        ws_host = args['ws_host'],
                                                        ws_port = args['ws_port'])
    wsforwarder.start()

def startFlaskInterface(args,sendQueue,receiveQueue):
    flaskiface = flaskinterface.FlaskInterface(flaskhost=args['flask_host'],
                                       flaskport=args['flask_port'],
                                       fake_data=args['fake_data'],
                                       verbose=args['verbose'],
                                       sendQueue=sendQueue,
                                       receiveQueue=receiveQueue,
                                       config_dir=args['config_dir'],
                                       logs_dir=args['logs_dir'])
    flaskiface.run()

def listener_configurer(args):
    logger = logging.getLogger("system")

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    filename = datetime.now().strftime("%d_%m_%y_%H_%M_%S_%f") + ".log"
    path = os.path.join(args['logs_dir'], "SystemLogs")
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, filename)
    file_handler = logging.FileHandler(file_path, "a")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def listener_process(args,queue, configurer):
    configurer(args)
    while True:
        try:
            record = queue.get()
            if record is None:
                break
            logger = logging.getLogger("system")
            logger.handle(record)
        except Exception:
            import sys, traceback
            print('Problem:', file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


if __name__ == '__main__':

    signal.signal(signal.SIGINT,exitBackend)
    signal.signal(signal.SIGTERM,exitBackend)

    logQueue = multiprocessing.Queue(-1) #TODO idk - chnage to some reasonable limit
    proclist['listener'] = multiprocessing.Process(target=listener_process,
                                       args=(argsin, logQueue, listener_configurer))
    proclist['listener'].start()

    
    sendQueue = multiprocessing.Queue()
    receiveQueue = multiprocessing.Queue()

    if not (argsin['fake_data']):
        if argsin.get('device',None) is None:
            raise Exception("No device passed")
        proclist['serialmanager'] = multiprocessing.Process(target=startSerialManager,args=(argsin,sendQueue,receiveQueue,logQueue))
        proclist['serialmanager'].start()

    #start flask interface process
    proclist['flaskinterface'] = multiprocessing.Process(target=startFlaskInterface,args=(argsin,sendQueue,receiveQueue))
    proclist['flaskinterface'].start()
    time.sleep(1)

    proclist['websocketforwarder'] = multiprocessing.Process(target=startWebSocketForwarder,args=(argsin,))
    proclist['websocketforwarder'].start()

    




 