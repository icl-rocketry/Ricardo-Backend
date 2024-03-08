
from queue import Empty, Full
from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit, send # added emit from flask_socketio
import multiprocessing as mp
import queue as q


from .taskhandler_webui import taskhandler_webui_bp
from .telemetry_webui import telemetry_webui_bp
from .command_webui import command_webui_bp
from .datarequesttaskhandler import DataRequestTaskHandler
from .emitter import Emitter

# system packages
import sys
# third-party packages
import eventlet # re-formatted eventlet comment



class FlaskInterface:


    def __init__(self,config_dir:str,logs_dir:str,sendQueue:mp.Queue = None,receiveQueue:mp.Queue = None,flaskhost="0.0.0.0", flaskport=5000, 
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

        # SYSTEM VARIABLES
        # thread-safe variables
        self.socketio_response_task_running:bool = False
        self.dummy_signal_running:bool = False
        self.sendQ = None

        self.flaskinterface_response_task_running:bool = False

        #data task request handler variables
        self.dtrh_receiveQ:mp.Queue = mp.Queue()

        self.app.add_url_rule('/packet', view_func=self.send_packet, methods=['POST'])
        self.app.add_url_rule('/response', view_func=self.get_response, methods=['GET'])
        self.socketio.on_event('connect',self.connect_telemetry,namespace='/telemetry')
        self.socketio.on_event('connect',self.dtrh_connect,namespace='/data_request_handler')
        self.socketio.on_event('connect',self.message_connect,namespace='/messages')
        self.socketio.on_event('connect',self.connect, namespace='/')
        self.socketio.on_event('connect',self.connect_command,namespace='/packet')
        self.socketio.on_event('send_data',self.send_data_event,namespace='/packet')
        self.socketio.on_event('disconnect',self.disconnect_command,namespace='/packet')

        self.__startFlaskInterface__(config_dir,logs_dir,sendQueue,receiveQueue,flaskhost, flaskport, fake_data,verbose)

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
                self.sendQ.put_nowait(sendData)
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

    def dtrh_connect(self):
        pass

    def message_connect(self):
        pass

    def connect(self):
        pass

    def connect_command(self):
        self.socketio_clients.append(request.sid)
        print("Client : " + request.sid + " joined command...")
        
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
            self.sendQ.put_nowait(sendData)
        except Full:
            print('[Flask-Inteface] Send Queue full, discarding packet!')
        
    def disconnect_command(self):
        print("Client : " + request.sid + " left command...")
        self.socketio_clients.remove(request.sid)

    # TASKS
    def startDataRequestHandler(self,config_dir:str,logs_dir:str,sendQ:mp.Queue,dtrh_receiveQ:mp.Queue,verbose:bool=False):
        datarequesthandler = DataRequestTaskHandler(self.socketio,config_dir,logs_dir,sendQ = sendQ,receiveQ = dtrh_receiveQ,verbose=verbose)
        datarequesthandler.mainloop()

    #socketio repsonse task
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
                print('[Flask-Interface]: rest response queue full, removing first item and pushing to queue!')
                self.rest_response_list[clientid].get()
                self.rest_response_list[clientid].put_nowait(item)

        else:
            self.rest_response_list[clientid] = q.Queue(maxsize=self.rest_response_queue_maxsize)
            self.rest_response_list[clientid].put_nowait(item)
    
        
    #socket io message queue task
    def __SocketIOMessageHandler__(self,message:dict):
        self.socketio.emit("new_message",message,namespace="/messages")

    # dummy signal
    def __DummySignalBroadcastTask__(self,verbose=False):
        # Create emitter
        emitter = Emitter(self.socketio, loop=True)

        # Run emitter until finished
        emitter.run()

        # Print exit message
        print('DummySignalBroadCastTask Killed')

    def __FlaskInterfaceResponseHandler__(self,receiveQ:mp.Queue,dtrh_receiveQ:mp.Queue):
        self.flaskinterface_response_task_running = True

        while self.flaskinterface_response_task_running:
            try:
                item:dict = receiveQ.get(block=False)  #expect a dict
                item_type = item['type'] #retrieve type of item
            
                if item_type == 'response':
                    #response data will have a dict of the following form
                    #{"identifier":identifier:dict,"data":responsedata:bytes}
                
                    try:
                        identifier:dict = item['identifier'] 
                    except KeyError:
                        print('[Flask-Interface]: identifier key not found in item') #TODO Log
                        continue
                    #identifier will be a dict which structure depends on the prticular applicaiton 
                    #for the flask interface we expct somethign like this
                    #{"prefix":"flaskinterface","process_id":"datataskrequesthandler","..."}
                    #we want the process_id here to figure out how to distributed
                    #to the sub applkication tasks i.e data task request handler and rest apis etcc
                    try:
                        process_identifier:str = identifier['process_id'] #TODO Log
                    except KeyError:
                        print('[Flask-Interface]: process_id key not found in item')
                        continue
                
                    # print(process_identifier)
                    if process_identifier == "DTRH":
                        try:
                            dtrh_receiveQ.put_nowait(item)
                        except Full:
                            print("[Flask-Interface] data task request handler queue full, discarding packet!")
                    elif process_identifier == "SIO":
                        self.__SocketIOResponseHandler__(item)
                    elif process_identifier == "REST":
                        self.__RESTAPIResponseHandler__(item)
                    else:
                        #need to use an actual logging library not just print statements...
                        print("[Flask-Interface] : task id not recognised")
                
                        
                        #try continue with life
                        # expect to catch badly formatted json
                elif item_type == 'logmessage':
                    #Log message data wil have a dict of the following form
                    #{"header":header_vars:dict,"message":str}
                    item.pop('type') #remove type field from item
                    self.__SocketIOMessageHandler__(item)
            except Empty:
                pass
            eventlet.sleep(0.001)
        
    # thread cleanup
    def cleanup(self,sig=None,frame=None): #ensure the telemetry broadcast thread has been killed
        
        self.dummy_signal_running = False
        self.flaskinterface_response_task_running = False

        eventlet.sleep(0.2)#allow threads to terminate

        print("\nFlask Interface Exited")

        sys.exit(0)
    
    def __startFlaskInterface__(self,config_dir:str,logs_dir:str,sendQueue:mp.Queue = None,receiveQueue:mp.Queue = None,flaskhost="0.0.0.0", flaskport=5000, 
                         fake_data=False,verbose=False):
    
        if (fake_data):
            # fake signal handler for ui testing only!!!
            fake_signal_filename = 'telemetry_log.txt'
            print("Reading fake signal from " + fake_signal_filename)
            print("Starting server on port " + str(flaskport) + "...")

            self.socketio.start_background_task(self.startDataRequestHandler,config_dir,logs_dir,mp.Queue,self.dtrh_receiveQ,verbose=verbose)
            self.socketio.start_background_task(self.__DummySignalBroadcastTask__,verbose=verbose)
            self.socketio.run(self.app, host=flaskhost, port=flaskport, debug=True, use_reloader=False)
            self.cleanup()

        else:

            if sendQueue is None or receiveQueue is None:
                print("No Send or Receive Queue Provided, Quiting!")

            else:  
                self.sendQ = sendQueue
                print("Server starting on port " + str(flaskport) + " ...")

                self.socketio.start_background_task(self.startDataRequestHandler,config_dir,logs_dir,self.sendQ,self.dtrh_receiveQ,verbose=verbose)
                self.socketio.start_background_task(self.__FlaskInterfaceResponseHandler__,receiveQueue,self.dtrh_receiveQ)
                self.socketio.run(self.app, host=flaskhost, port=flaskport, debug=False, use_reloader=False)

            self.cleanup()

if __name__ == "__main__":
    FlaskInterface(flaskport=1337, fake_data=True)