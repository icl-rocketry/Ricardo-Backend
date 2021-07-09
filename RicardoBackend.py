import argparse
import re
import signal
import sys
from Interfaces import commandlineinterface
from Interfaces import flaskinterface
from RicardoHandler import serialmanager
from RicardoHandler import telemetryhandler
from multiprocessing import Process
import redis

# Argument Parsing
ap = argparse.ArgumentParser()
ap.add_argument("-d", "--device", required=True, help="Ricardo Serial Port", type=str)
ap.add_argument("-b", "--baud", required=False, help="Serial Port Baud Rate", type=int,default=115200)
ap.add_argument("--flask-host", required=False, help="flask host", type=str,default="0.0.0.0")
ap.add_argument("--flask-port", required=False, help="flask Port", type=int,default = 1337)
ap.add_argument("-v", "--verbose", required=False, help="Enable Verbose Mode", action='store_true')
ap.add_argument("--redis-host", required=False, help="redis host", type=str,default = "localhost")
ap.add_argument("--redis-port", required=False, help="redis port", type=int,default = 6379)
ap.add_argument('-c','--cli', required=False, help="Enable Interactive Commmand Line Interface",action='store_true',default=False)

args = vars(ap.parse_args())


def exitBackend(signalNumber, frame):
    global telemetrytask,sm
    # f.stop()
    #flask_thread.join()
    #flaskinterface.bg_exit_event.set()
    telemetrytask.stop()
    flaskinterface.stopFlaskInterface()
    sm.stop() #halt serial manager process
    sys.exit(0)

def checkRedis():
    try:
        server = redis.Redis(host=args["redis_host"],port=args["redis_port"])
        server.ping()
    except redis.exceptions.ConnectionError:
        errormsg = "[ERROR] -> Redis server not found at host:'" + args["redis_host"] + "' port:" + str(args["redis_port"]) + "\nPlease check redis is running"
        sys.exit(errormsg)

if __name__ == '__main__':
    tasklist = []
    signal.signal(signal.SIGINT, exitBackend)
    signal.signal(signal.SIGTERM, exitBackend)

    #check redis server is running
    checkRedis()

   

    #start serial maanger process
    sm = serialmanager.SerialManager(device = args["device"],
                                     baud = args["baud"],
                                     redishost = args["redis_host"],
                                     redisport=args["redis_port"])
    sm.start() 
    #start telemetry handler process
    telemetrytask = telemetryhandler.TelemetryHandler(redishost = args["redis_host"],
                                                      redisport=args["redis_port"])
    tasklist.append(telemetrytask.get_id()) #add task id to running task list
    telemetrytask.start()
    #start flask interface process
    p = Process(target=flaskinterface.startFlaskInterface,args=(args['flask_host'],
                                                                args['flask_port'],
                                                                args['redis_host'],
                                                                args['redis_port'],))
    p.start()

    
    
    if (args['cli']):
        c = commandlineinterface.CommandLineInterface(redishost=args['redis_host'],
                                                      redisport=args['redis_port'],
                                                      tasklist=tasklist
                                                      )
        #c.cmdloop() #start cmd event loop
        c.preloop()
        c._cmdloop()
        c.postloop()
        # while True:

        





 