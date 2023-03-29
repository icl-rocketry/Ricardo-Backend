import multiprocessing
import argparse
import signal
import sys
import redis
import time

from ricardobackend.flaskinterface import flaskinterface
from ricardobackend.flaskinterface import datarequesttaskhandler

from ricardobackend.serialmanager import serialmanager




# Argument Parsing
ap = argparse.ArgumentParser()
ap.add_argument("-d", "--device", required=True, help="Ricardo Serial Port", type=str)
ap.add_argument("-b", "--baud", required=False, help="Serial Port Baud Rate", type=int,default=115200)
ap.add_argument("--flask-host", required=False, help="flask host", type=str,default="0.0.0.0")
ap.add_argument("--flask-port", required=False, help="flask Port", type=int,default = 1337)
ap.add_argument("-v", "--verbose", required=False, help="Enable Verbose Mode", action='store_true')
ap.add_argument("--redis-host", required=False, help="redis host", type=str,default = "localhost")
ap.add_argument("--redis-port", required=False, help="redis port", type=int,default = 6379)
ap.add_argument('-mon','--monitor', required=False, help="Enable network monitoring ",action='store_true',default=False)
ap.add_argument('-monip','--monitor-ip', required=False, help="Set network monitoring ip",type=str,default = "127.0.0.1")
ap.add_argument('-monport','--monitor-port', required=False, help="Set network monitoring port",type=int,default = 7000)

argsin = vars(ap.parse_args())


def exitBackend(proclist):
    for key in proclist:
        print("Killing: " + key + " Pid: " + str(proclist[key].pid))
        proclist[key].terminate()
        proclist[key].join()

    proclist = {}

    sys.exit(0)


def checkRedis():
    try:
        server = redis.Redis(host=argsin["redis_host"],port=argsin["redis_port"])
        server.ping()
    except redis.exceptions.ConnectionError:
        errormsg = "[ERROR] -> Redis server not found at host:'" + argsin["redis_host"] + "' port:" + str(argsin["redis_port"]) + "\nPlease check redis is running"
        sys.exit(errormsg)

def startSerialManager(args):

    serman = serialmanager.SerialManager(device = args["device"],
                                     baud = args["baud"],
                                     redishost = args["redis_host"],
                                     redisport=args["redis_port"],
                                     UDPMonitor=args['monitor'],
                                     UDPIp=args['monitor_ip'],
                                     UDPPort=args["monitor_port"],
                                     verbose=args['verbose'])
    serman.run()


if __name__ == '__main__':
    proclist = {}
    #check redis server is running
    checkRedis()

    proclist['serialmanager'] = multiprocessing.Process(target=startSerialManager,args=(argsin,))
    proclist['serialmanager'].start()
    
    #start flask interface process
    proclist['flaskinterface'] = multiprocessing.Process(target=flaskinterface.startFlaskInterface,args=(argsin['flask_host'],
                                                                                            argsin['flask_port'],
                                                                                            argsin['redis_host'],
                                                                                            argsin['redis_port'],))
    proclist['flaskinterface'].start()

    while(True):
        pass

    exitBackend(proclist)





 