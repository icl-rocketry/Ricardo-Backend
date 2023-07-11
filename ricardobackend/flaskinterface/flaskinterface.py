# PACKAGES
# flask packages
from queue import Empty, Full
from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit, send # added emit from flask_socketio
import multiprocessing as mp
import queue as q


from .taskhandler_webui import taskhandler_webui_bp
from .telemetry_webui import telemetry_webui_bp
from .command_webui import command_webui_bp
from .datarequesttaskhandler import DataRequestTaskHandler
from .emitter import EmitterClass


# if __name__ == "__main__":
#     from telemetry_webui.telemetry_webui import telemetry_webui_bp
#     from command_webui.command_webui import command_webui_bp
#     # from datarequesttaskhandler import DataRequestTaskHandler
# else:
#     from .telemetry_webui.telemetry_webui import telemetry_webui_bp
#     from .command_webui.command_webui import command_webui_bp
#     from .datarequesttaskhandler import DataRequestTaskHandler
    
# system packages
import sys
# third-party packages
import eventlet # re-formatted eventlet comment
'''
Dont Monkey Patch 
this module is started as a multiprocessing process in the RicardoBackend.py 
module. If we monkey patch, we monkey patch everything else imported. We can 
get away with this here as we make sure to not use anything requiring monkey 
patch i.e using socketio.start_background_task() instead of starting the thread 
with python threading. Eventlet monkey patch changes the memory location of 
threading.current_thread resulting in (threading.current_tread() is 
threading.main_thread() returning false which breaks cmd2...
'''

# APP INITIALIZATION
# flask app 
app = Flask(__name__)
app.register_blueprint(command_webui_bp, url_prefix="/command_ui")
app.register_blueprint(telemetry_webui_bp, url_prefix="/telemetry_ui")
app.register_blueprint(taskhandler_webui_bp, url_prefix="/taskhandler_ui")

# app = Flask(__name__, static_folder='static/react')
#app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
app.config['DEBUG'] = False
# socketio app
socketio = SocketIO(app,cors_allowed_origins="*",async_mode='eventlet',logger=True)
socketio_clients = []
#flask rest api variables
rest_response_queue_maxsize = 10
rest_response_list = None #this will be a dict mapping to queues {"clientid1":Queue,"clientid2":Queue}

# SYSTEM VARIABLES
# thread-safe variables
socketio_response_task_running:bool = False
dummy_signal_running:bool = False
sendQ = None

flaskinterface_response_task_running:bool = False

#data task request handler variables
# dtrh_receiveQ_maxsize = 1000
dtrh_receiveQ:mp.Queue = mp.Queue()

# misc
prev_time = 0
updateTimePeriod = 0.01 #in seconds



# FLASK APP 
# new / route: return react site
# @app.route('/', defaults={'path': ''})
# @app.route('/<path:path>')
# def serve(path):
#     if path != "" and os.path.exists(app.static_folder + '/' + path):
#         return send_from_directory(app.static_folder, path)
#     else:
#         # return send_from_directory(app.static_folder, 'index.html')
#         return render_template('index.html')



@app.route('/packet', methods=['POST'])
def send_packet():
    global sendQ
    packet_data = request.json
    print('POST DATA')
    print(packet_data)
    if packet_data == None:
        return 'Bad Request',400
    if all (keys in packet_data for keys in ("data","clientid")):

        identifier = {"prefix":"flaskinterface","process_id":"REST","clientid":packet_data['clientid']}
        sendData = {'data':packet_data.get('data'),
                    'identifier':identifier}
        try:
            sendQ.put_nowait(sendData)
        except Full:
            print('[Flask-Inteface] Send Queue full, discarding packet!')

        # r.lpush("SendQueue",json.dumps(packet_data))
        return 'OK',200
    else:
        return 'Bad Request',400

@app.route('/response', methods=['GET'])
def get_response():
    args = request.args
    args.to_dict()

    clientid = args.get("clientid")
    
    if clientid is not None:
        if clientid in rest_response_list.keys():
            received_response = rest_response_list[clientid].get('data').hex()
            return received_response,200
        else:
            return "NODATA",200
    else:
        return 'Bad Request \nNo Client ID supplied',400


# SOCKETIO APP
@socketio.on('connect',namespace='/telemetry')
def connect_telemetry():
    # maybe emit the newest telemetry so connecting clients know whats up
    pass

@socketio.on('connect', namespace='/data_request_handler')
def connect():
    pass

@socketio.on('connect', namespace='/')
def connect():
    pass

@socketio.on('connect',namespace='/packet')
def connect_command():
    global socketio_clients
    socketio_clients.append(request.sid)
    print("Client : " + request.sid + " joined command...")
    
@socketio.on('send_data',namespace='/packet')
def send_data_event(data):
    global sendQ
    packetData = data
    if 'data' not in packetData.keys():
        emit('Error',{'Error':'No Data!'},namespace='/packet')
        return
    identifier = {"prefix":"flaskinterface","process_id":"SIO","sid":str(request.sid)}
    sendData = {'data':packetData.get('data'),
                'identifier':identifier}
    # r.lpush("SendQueue",json.dumps(sendData))
    try:
        sendQ.put_nowait(sendData)
    except Full:
        print('[Flask-Inteface] Send Queue full, discarding packet!')
    

@socketio.on('disconnect',namespace='/packet')
def disconnect_command():
    global socketio_clients
    print("Client : " + request.sid + " left command...")
    socketio_clients.remove(request.sid)


# TASKS
def startDataRequestHandler(sendQ:mp.Queue,dtrh_receiveQ:mp.Queue,verbose:bool=False):
    datarequesthandler = DataRequestTaskHandler(socketio,sendQ = sendQ,receiveQ = dtrh_receiveQ,verbose=verbose)
    datarequesthandler.mainloop()

#socketio repsonse task

def __SocketIOResponseHandler__(item):
    sid = (item.get('identifier',None)).get('sid',None)
    if sid is None:
        print('Identifier badly formed')
        print(item)
        return
    
    print(sid)
    print(socketio_clients)

    if sid in socketio_clients:
        responseData = item.get('data')

        response = {'data':str(responseData.hex())}
        print(response)

        socketio.emit('response',response,to=sid,namespace='/packet')

def __RESTAPIResponseHandler__(item):
    global rest_response_list
    clientid = (item.get('identifier',None)).get('clientid',None)
    if clientid is None:
        print('Identifier badly formed')
        print(item)
        return
   
  
    if clientid in rest_response_list.keys():
        try:
            rest_response_list[clientid].put_nowait(item)
        except Full:
            print('[Flask-Interface]: rest response queue full, removing first item and pushing to queue!')
            rest_response_list[clientid].get()
            rest_response_list[clientid].put_nowait(item)

    else:
        rest_response_list[clientid] = q.Queue(maxsize=rest_response_queue_maxsize)
        rest_response_list[clientid].put_nowait(item)
   
    
    

#socket io message queue task
def __SocketIOMessageHandler__(message:dict):
    socketio.emit("new_message",message,namespace="/messages")


# dummy signal
def __DummySignalBroadcastTask__(verbose=False):
    global dummy_signal_running
    dummy_signal_running = True
    e = EmitterClass(socketio,'telemetry-log',verbose=verbose)
    while dummy_signal_running:
        e.emit() #call emit
    print('DummySignalBroadCastTask Killed')

def __FlaskInterfaceResponseHandler__(receiveQ:mp.Queue,dtrh_receiveQ:mp.Queue):
    global flaskinterface_response_task_running
    flaskinterface_response_task_running = True

    while flaskinterface_response_task_running:
        try:
            item:dict = receiveQ.get(block=False)  #expect a dict
            item_type = item['type'] #retrieve type of item
            if item_type == 'response':
                #response data will have a dict of the following form
                #{"identifier":identifier:dict,"data":responsedata:bytes}
             
                try:
                    identifier:dict = item['identifier'] 
                except KeyError:
                    print('[Flask-Interface]: identifier key not found in item')
                    continue
                #identifier will be a dict which structure depends on the prticular applicaiton 
                #for the flask interface we expct somethign like this
                #{"prefix":"flaskinterface","process_id":"datataskrequesthandler","..."}
                #we want the process_id here to figure out how to distributed
                #to the sub applkication tasks i.e data task request handler and rest apis etcc
                try:
                     process_identifier:str = identifier['process_id']
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
                    __SocketIOResponseHandler__(item)
                elif process_identifier == "REST":
                    __RESTAPIResponseHandler__(item)
                else:
                    #need to use an actual logging library not just print statements...
                    print("[Flask-Interface] : task id not recognised")
            
                    
                    #try continue with life
                    # expect to catch badly formatted json
            elif item_type == 'logmessage':
                #Log message data wil have a dict of the following form
                #{"header":header_vars:dict,"message":str}
                item.pop('type') #remove type field from item
                __SocketIOMessageHandler__(item)
        except Empty:
            pass
        eventlet.sleep(0.001)


    

# thread cleanup
def cleanup(sig=None,frame=None): #ensure the telemetry broadcast thread has been killed
    global dummy_signal_running,flaskinterface_response_task_running
    
    dummy_signal_running = False
    flaskinterface_response_task_running = False

    eventlet.sleep(0.2)#allow threads to terminate

    print("\nFlask Interface Exited")

    sys.exit(0)


# DUTY FUNCTION
def startFlaskInterface(sendQueue:mp.Queue = None,receiveQueue:mp.Queue = None,flaskhost="0.0.0.0", flaskport=5000, 
                         fake_data=False,verbose=False):
    
    if (fake_data):
        # fake signal handler for ui testing only!!!
        fake_signal_filename = 'telemetry_log.txt'
        print("Reading fake signal from " + fake_signal_filename)
        print("Starting server on port " + str(flaskport) + "...")

        socketio.start_background_task(startDataRequestHandler,mp.Queue,dtrh_receiveQ,verbose=verbose)
        socketio.start_background_task(__DummySignalBroadcastTask__,verbose=verbose)
        socketio.run(app, host=flaskhost, port=flaskport, debug=True, use_reloader=False)
        cleanup()

    else:
        global sendQ

        if sendQueue is None or receiveQueue is None:
            print("No Send or Receive Queue Provided, Quiting!")

        else:  
            sendQ = sendQueue
            print("Server starting on port " + str(flaskport) + " ...")

            socketio.start_background_task(startDataRequestHandler,sendQ,dtrh_receiveQ,verbose=verbose)
            socketio.start_background_task(__FlaskInterfaceResponseHandler__,receiveQueue,dtrh_receiveQ)
            socketio.run(app, host=flaskhost, port=flaskport, debug=False, use_reloader=False)

        cleanup()

        
if __name__ == "__main__":
    startFlaskInterface(flaskport=1337, fake_data=True)