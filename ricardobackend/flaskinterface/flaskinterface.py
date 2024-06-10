
from queue import Empty, Full
from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit, send # added emit from flask_socketio
import multiprocessing as mp
import queue as q
import time
import simplejson


from .taskhandler_webui import taskhandler_webui_bp
from .telemetry_webui import telemetry_webui_bp
from .command_webui import command_webui_bp
from .datarequesttaskhandler import DataRequestTaskHandler
from .emitter import Emitter

# system packages
import sys
# third-party packages
import eventlet # re-formatted eventlet comment

import logging
import logging.handlers


class FlaskInterface:


    def __init__(self,config_dir:str,logs_dir:str,sendQueue:mp.Queue = None,receiveQueue:mp.Queue = None,logQ:mp.Queue = None,flaskhost="0.0.0.0", flaskport=5000, 
                         fake_data=False,verbose=False):

        # flask app 
        self.app = Flask(__name__)
        self.app.register_blueprint(command_webui_bp, url_prefix="/command_ui")
        self.app.register_blueprint(telemetry_webui_bp, url_prefix="/telemetry_ui")
        self.app.register_blueprint(taskhandler_webui_bp, url_prefix="/taskhandler_ui")


        self.app.config["SECRET_KEY"] = "secret!"
        self.app.config['DEBUG'] = False
        
        # socketio app
        self.socketio = SocketIO(self.app,cors_allowed_origins="*",async_mode='eventlet',logger=False)
        self.socketio_clients = []
        #flask rest api variables
        self.rest_response_queue_maxsize = 100
        self.rest_response_list = None #this will be a dict mapping to queues {"clientid1":Queue,"clientid2":Queue}

        self.socketio_response_task_running:bool = False
        self.dummy_signal_running:bool = False
        self.flaskinterface_response_task_running:bool = False

        self.sendQueue = sendQueue
        self.receiveQueue = receiveQueue
        self.logQueue = logQ
        self.flaskhost = flaskhost
        self.flaskport = flaskport
        self.fake_data = fake_data
        self.verbose = verbose
        self.config_dir = config_dir
        self.logs_dir = logs_dir


        #data task request handler variables
        self.dtrh_receiveQ:mp.Queue = mp.Queue()

        self.app.add_url_rule('/packet', view_func=self.send_packet, methods=['POST'])
        self.app.add_url_rule('/response', view_func=self.get_response, methods=['GET'])

        self.socketio.on_event('connect',self.connect_telemetry,namespace='/telemetry')
        self.socketio.on_event('connect',self.connect, namespace='/')
        self.socketio.on_event('connect',self.connect_command,namespace='/packet')
        self.socketio.on_event('connect',self.connect_command,namespace='/system_events')

        self.socketio.on_event('send_data',self.send_data_event,namespace='/packet')
        self.socketio.on_event('forward_event',self.forward_system_event,namespace='/system_events')

        self.socketio.on_event('disconnect',self.disconnect_command,namespace='/packet')

        # self.__startFlaskInterface__(config_dir,logs_dir,sendQueue,receiveQueue,flaskhost, flaskport, fake_data,verbose)

        # logging
        queue_handler = logging.handlers.QueueHandler(self.logQueue)
        self.logger = logging.getLogger("system")
        self.logger.addHandler(queue_handler)
        if verbose:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)


    def send_packet(self):

        packet_data = request.json
        print('POST DATA') #TODO: Verbosity levels?
        print(packet_data)
        if packet_data == None:
            return 'Bad Request',400
        if all (keys in packet_data for keys in ("data","clientid")):
            ##TODO:DRY
            identifier = {"prefix":"flaskinterface","process_id":"REST","clientid":packet_data['clientid']}
            sendData = {'data':packet_data.get('data'),
                        'identifier':identifier}
            try:
                self.sendQueue.put_nowait(sendData)
            except Full:
                print('[Flask-Inteface] Send Queue full, discarding packet!')

            return 'OK',200
        else:
            return 'Bad Request',400
        
    def get_response(self):

        args = request.args
        args.to_dict()

        clientid = args.get("clientid")
        
        if clientid is not None:
            if clientid in self.rest_response_list.keys():
                received_response = self.rest_response_list[clientid].get('data').hex()
                return received_response,200
            else:
                return "NODATA",200
        else:
            return 'Bad Request \nNo Client ID supplied',400
   
    #TODO refactor this socketio bit
    # SOCKETIO APP
        
    def connect_telemetry(self):
        # maybe emit the newest telemetry so connecting clients know whats up
        pass

    def connect(self):
        pass

    def connect_command(self):
        self.socketio_clients.append(request.sid)
        #print("Client : " + request.sid + " joined command...")
        msg = "Client : " + request.sid + " joined command..."
        self.__flaskint_log__(msg, level=logging.INFO)

    def connect_system_events(self):
        pass
    
    def forward_system_event(self,event):
        source_data = event["source"]
        source_data['SIO_ID']  = request.sid
        self.__SystemEventHandler__(event) #forward evenet and broadcast

    def send_data_event(self,data):
        packetData = data
        ##TODO:DRY!!
        if 'data' not in packetData.keys():
            emit('Error',{'Error':'No Data!'},namespace='/packet')
            return
        identifier = {"prefix":"flaskinterface","process_id":"SIO","sid":str(request.sid)}
        sendData = {'data':packetData.get('data'),
                    'identifier':identifier}
        try:
            self.sendQueue.put_nowait(sendData)
        except Full:
            #print('[Flask-Inteface] Send Queue full, discarding packet!')
            self.__flaskint_log__('Send Queue full, discarding packet!', level=logging.ERROR)
            
        
    def disconnect_command(self):
        #print("Client : " + request.sid + " left command...")
        msg = "Client : " + request.sid + " left command..."
        self.__flaskint_log__(msg, level=logging.INFO)
        self.socketio_clients.remove(request.sid)
    # TASKS
    def startDataRequestHandler(self):
        datarequesthandler = DataRequestTaskHandler(self.socketio,self.config_dir,self.logs_dir, sendQ = self.sendQueue,receiveQ = self.dtrh_receiveQ, logQ = self.logQueue, verbose=self.verbose)
        datarequesthandler.mainloop()

    def __SocketIOResponseHandler__(self,item):
        sid = (item.get('identifier',None)).get('sid',None)
        if sid is None:
            print('Identifier badly formed')
            print(item)
            return
        
        print(sid)
        print(self.socketio_clients)

        if sid in self.socketio_clients:
            responseData = item.get('data')

            response = {'data':str(responseData.hex())}
            print(response)

            self.socketio.emit('response',response,to=sid,namespace='/packet')

    def __RESTAPIResponseHandler__(self,item):
        self.rest_response_list
        clientid = (item.get('identifier',None)).get('clientid',None)
        if clientid is None:
            print('Identifier badly formed')
            print(item)
            return
    
    
        if clientid in self.rest_response_list.keys():
            try:
                self.rest_response_list[clientid].put_nowait(item)
            except Full:
                #print('[Flask-Interface]: rest response queue full, removing first item and pushing to queue!')
                self.__flaskint_log__('REST response queue full, removing first item and pushing to queue!', level=logging.WARNING)
                self.rest_response_list[clientid].get()
                self.rest_response_list[clientid].put_nowait(item)

        else:
            self.rest_response_list[clientid] = q.Queue(maxsize=self.rest_response_queue_maxsize)
            self.rest_response_list[clientid].put_nowait(item)
            
    def __SystemEventHandler__(self,event:dict):
        '''
        {
        "SystemEvent":
            {
                "level":"", // info critical debug error warn
                "name":"", //Ignition Command, Rocket Log, TVCArm Command
                "msg":"", 
                "time":"",
                "souce":{
                    application:
                    ip:
                    rnp: RnpHeader vars
                    }
            }
        }
        '''
        self.socketio.emit("new_event",simplejson.dumps(event),namespace="/system_events")  
        #TODO Log to system log file!
 
    def __DummySignalBroadcastTask__(self):
        # Create emitter
        emitter = Emitter(self.socketio, loop=True)

        # Run emitter until finished
        emitter.run()

        # Print exit message
        #print('DummySignalBroadCastTask Killed')
        self.__flaskint_log__('DummySignalBroadCastTask Killed', level=logging.DEBUG)

        

    def __FlaskInterfaceResponseHandler__(self):
        self.flaskinterface_response_task_running = True

        while self.flaskinterface_response_task_running:
            try:
                item:dict = self.receiveQueue.get(block=False)  #expect a dict
                item_type = item['type'] #retrieve type of item
            
                if item_type == 'response':
                    #response data will have a dict of the following form
                    #{"identifier":identifier:dict,"data":responsedata:bytes}
                
                    try:
                        identifier:dict = item['identifier'] 
                    except KeyError:
                        #print('[Flask-Interface]: identifier key not found in item') #TODO Log
                        self.__flaskint_log__('Identifier key not found in item', level=logging.ERROR)
                        continue
                    #identifier will be a dict which structure depends on the prticular applicaiton 
                    #for the flask interface we expct somethign like this
                    #{"prefix":"flaskinterface","process_id":"datataskrequesthandler","..."}
                    #we want the process_id here to figure out how to distributed
                    #to the sub applkication tasks i.e data task request handler and rest apis etcc
                    try:
                        process_identifier:str = identifier['process_id'] #TODO Log
                    except KeyError:
                        #print('[Flask-Interface]: process_id key not found in item')
                        self.__flaskint_log__('Process_id key not found in item', level=logging.ERROR)
                        continue
                
                    # print(process_identifier)
                    if process_identifier == "DTRH":
                        try:
                            self.dtrh_receiveQ.put_nowait(item)
                        except Full:
                            #print("[Flask-Interface] data task request handler queue full, discarding packet!")
                            self.__flaskint_log__('Data task request handler queue full, discarding packet!', level=logging.ERROR)
                    elif process_identifier == "SIO":
                        self.__SocketIOResponseHandler__(item)
                    elif process_identifier == "REST":
                        self.__RESTAPIResponseHandler__(item)
                    else:
                        #TODO need to use an actual logging library not just print statements...
                        #print("[Flask-Interface] : task id not recognised")
                        self.__flaskint_log__('Task id not recognised', level=logging.ERROR)

            
                        
                        #try continue with life
                        # expect to catch badly formatted json
                elif item_type == 'logmessage':
                    #Log message data wil have a dict of the following form
                    #{"header":header_vars:dict,"message":str}
                    item.pop('type') #remove type field from item
                    # self.__SocketIOMessageHandler__(item)
                    event = {
                        "level":"info",
                        "name":"Rocket Log",
                        "msg":item["message"],
                        "time":time.time_ns()*(1e-6), #conversion to milliseconds?? idk
                        "source":{
                                    "application":"Ricardo-Backend", #TODO maybe add versioning?
                                    "ip":"",
                                    "rnp":item["header"]
                                }
                        }
                    self.__SystemEventHandler__(event)
            except Empty:
                pass
            eventlet.sleep(0.001)
        
    # thread cleanup
    def cleanup(self,sig=None,frame=None): #ensure the telemetry broadcast thread has been killed
        
        self.dummy_signal_running = False
        self.flaskinterface_response_task_running = False

        eventlet.sleep(0.2)#allow threads to terminate

        #print("\nFlask Interface Exited")
        self.__flaskint_log__('Flask Interface Exited', level=logging.INFO)

        sys.exit(0)


    def run(self):
        
        #print("Starting server on port " + str(self.flaskport) + "...") #todo logging
        msg = "Starting server on port " + str(self.flaskport) + "..."
        self.__flaskint_log__(msg, level=logging.INFO)

        if (self.fake_data):
            # fake signal handler for ui testing only!!!
            fake_signal_filename = 'telemetry_log.txt' #is this even required?
            #print("Reading fake signal from " + fake_signal_filename)
            msg = "Reading fake signal from " + fake_signal_filename
            self.__flaskint_log__(msg, level=logging.DEBUG)
            

            self.socketio.start_background_task(self.startDataRequestHandler)
            self.socketio.start_background_task(self.__DummySignalBroadcastTask__)
            self.socketio.run(self.app, host=self.flaskhost, port=self.flaskport, debug=True, use_reloader=False)

        else:

            if self.sendQueue is None or self.receiveQueue is None:
                #print("No Send or Receive Queue Provided, Quiting!") #TODO Logging
                self.__flaskint_log__('No Send or Receive Queue Provided, Quiting!', level=logging.CRITICAL)

            else:  
                self.socketio.start_background_task(self.startDataRequestHandler)
                self.socketio.start_background_task(self.__FlaskInterfaceResponseHandler__)
                self.socketio.run(self.app, host=self.flaskhost, port=self.flaskport, debug=False, use_reloader=False)

        self.cleanup()

    def __flaskint_log__(self, msg, level=logging.DEBUG):
        message = '[Flask Interface] - ' + str(msg)
        self.logger.log(level, message)
        
if __name__ == "__main__":
    FlaskInterface(flaskport=1337, fake_data=True)