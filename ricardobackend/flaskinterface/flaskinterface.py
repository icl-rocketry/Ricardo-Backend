# PACKAGES
# flask packages
from queue import Empty
from flask import Flask, jsonify, request, Response, render_template, send_from_directory
from flask_socketio import SocketIO, emit, send # added emit from flask_socketio


from .telemetry_webui import telemetry_webui_bp
from .command_webui import command_webui_bp
from .datarequesttaskhandler import DataRequestTaskHandler


# if __name__ == "__main__":
#     from telemetry_webui.telemetry_webui import telemetry_webui_bp
#     from command_webui.command_webui import command_webui_bp
#     # from datarequesttaskhandler import DataRequestTaskHandler
# else:
#     from .telemetry_webui.telemetry_webui import telemetry_webui_bp
#     from .command_webui.command_webui import command_webui_bp
#     from .datarequesttaskhandler import DataRequestTaskHandler
    
# system packages
import time
import redis
import json
import signal
import sys
import os
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

# app = Flask(__name__, static_folder='static/react')
#app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
app.config['DEBUG'] = False
# socketio app
socketio = SocketIO(app,cors_allowed_origins="*",async_mode='eventlet',logger=True)
socketio_clients = []

# SYSTEM VARIABLES
# thread-safe variables
socketio_response_task_running:bool = False
socketio_message_queue_task_running:bool = False
dummy_signal_running:bool = False

# redis variables
r : redis.Redis = None
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
    packet_data = request.json
    print('POST DATA')
    print(packet_data)
    if packet_data == None:
        return 'Bad Request',400
    if all (keys in packet_data for keys in ("data","clientid")):
        r.lpush("SendQueue",json.dumps(packet_data))
        return 'OK',200
    else:
        return 'Bad Request',400

@app.route('/response', methods=['GET'])
def get_response():
    args = request.args
    args.to_dict()

    clientid = args.get("clientid")
    
    if clientid is not None:
        key = "ReceiveQueue:" + str(clientid)
        if r.llen(key) > 0 :
            received_response :bytes = r.rpop(key)
            return received_response,200
        else:
            return "NODATA",200
    else:
        return 'Bad Request \nNo Client ID supplied',400

@app.route('/telemetry', methods=['GET'])
def get_telemetry():
    #get telemetry data from redis db
    #the telemetry key will be a json object
    #prcess the request args to retrieve task_id
    args = request.args
    print(args)
    args.to_dict()
    task_id:str = "telemetry:" + args.get("task_id")
    if r is None:
        return '''Redis client not setup in flaskinterface.py, 
        likely you are running the flaskinterface.py directly... 
        If you aren't, check that redis is running and is correctly 
        being setup when flaskinterface is being called''',503
    telemetry_data = r.get(task_id)
    if telemetry_data is not None:
        return json.loads(telemetry_data),200
    else:
        return "NODATA",200

@app.route("/graph",methods=['get']) # -> depreciated, prefer using flask blueprints to serve
def get_graph():
    return render_template('graph.html',x_window = 100)

@app.route("/map",methods=['get']) # -> depreciated, prefer using flask blueprints to serve
def get_map():
    return render_template('map.html',x_window = 100)


# SOCKETIO APP
@socketio.on('connect',namespace='/telemetry')
def connect_telemetry():
    # maybe emit the newest telemetry so connecting clients know whats up
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
    packetData = data
    if 'data' not in packetData.keys():
        emit('Error',{'Error':'No Data!'},namespace='/packet')
        return
    
    sendData = {'data':packetData.get('data'),
                'clientid':'LOCAL:SOCKETIO:'+str(request.sid)}
    r.lpush("SendQueue",json.dumps(sendData))
    

@socketio.on('disconnect',namespace='/packet')
def disconnect_command():
    global socketio_clients
    print("Client : " + request.sid + " left command...")
    socketio_clients.remove(request.sid)


# TASKS
def startDataRequestHandler(redis_host,redis_port):
    datarequesthandler = DataRequestTaskHandler(socketio,redishost=redis_host,redisport=redis_port)
    datarequesthandler.mainloop()

#socketio repsonse task
def __SocketIOResponseTask__(redishost,redisport):
    global socketio_response_task_running,socketio_clients
    socketio_response_task_running = True

    redis_connection = redis.Redis(host=redishost,port=redisport)

    while socketio_response_task_running:
        keylist = list(redis_connection.scan_iter('ReceiveQueue:LOCAL:SOCKETIO:*',1)) #find keys with the prefix 
        if keylist: #check we got keys
            key = keylist[0] #only process 1 key at a time
            key_string:str = bytes(key).decode("UTF-8")
            # sid = key_string.removeprefix('ReceiveQueue:LOCAL:SOCKETIO:') #only works with py3.9
            sid = key_string[len('ReceiveQueue:LOCAL:SOCKETIO:'):]

            print(key)
            print(socketio_clients)

            if sid in socketio_clients:
                redis_connection.persist(key) #remove key timeout
                responseData:bytes = redis_connection.rpop(key)
                response = {'Data':str(responseData.hex())}
                print(response)

                socketio.emit('Response',response,to=sid,namespace='/packet')

            else:
                redis_connection.delete(key)#delete the whole receive queue as client is no longer connected     
        
        eventlet.sleep(0.005)

    print("SocketIOResponseTask Killed")

#socket io message queue task
def __SocketIOMessageQueueTask__(redishost,redisport):
    global socketio_message_queue_task_running
    socketio_message_queue_task_running = True

    redis_connection = redis.Redis(host=redishost,port=redisport)

    while socketio_message_queue_task_running:
        eventlet.sleep(0.005)# sleep for update time 
        data = redis_connection.rpop("MessageQueue")
        if data is not None:
           socketio.emit("new_message",json.dumps(json.loads(data)),namespace="/messages")
    print("SocketIOMessageQueueTask Killed")

# dummy signal
def __DummySignalBroadcastTask__():
    from emitter import emitter
    global dummy_signal_running
    dummy_signal_running = True
    e = emitter.EmitterClass('telemetry-log')
    while dummy_signal_running:
        e.emit() #call emit
    print('DummySignalBroadCastTask Killed')


# thread cleanup
def cleanup(sig=None,frame=None): #ensure the telemetry broadcast thread has been killed
    global dummy_signal_running, socketio_response_task_running
    
    dummy_signal_running = False
    socketio_response_task_running = False

    eventlet.sleep(0.2)#allow threads to terminate

    print("\nFlask Interface Exited")

    sys.exit(0)


# DUTY FUNCTION
def startFlaskInterface(flaskhost="0.0.0.0", flaskport=5000, 
                        redishost='localhost', redisport=6379, real_data=True):
    # original signal handler
    if (real_data):
        global r
        print("Server starting on port " + str(flaskport) + " ...")

        r = redis.Redis(redishost,redisport)

        socketio.start_background_task(startDataRequestHandler,redishost,redisport)
        socketio.start_background_task(__SocketIOResponseTask__,redishost,redisport)
        socketio.start_background_task(__SocketIOMessageQueueTask__,redishost,redisport)
        socketio.run(app, host=flaskhost, port=flaskport, debug=False, use_reloader=False)
        cleanup()

    # fake signal handler for ui testing only!!!
    else:
        # server logs
        fake_signal_filename = 'telemetry_log.txt'
        print("Reading fake signal from " + fake_signal_filename)
        print("Starting server on port " + str(flaskport) + "...")

        socketio.start_background_task(__DummySignalBroadcastTask__)
        socketio.run(app, host=flaskhost, port=flaskport, debug=True, use_reloader=False)
        cleanup()

        
if __name__ == "__main__":
    startFlaskInterface(flaskport=1337, real_data=False)