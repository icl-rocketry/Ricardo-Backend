import socketio

# standard Python
sio = socketio.Client(logger=True, engineio_logger=True)

sio.connect('http://localhost:1337/',namespaces=['/','/telemetry','/packet'])


@sio.event
def connect():
    print("I'm connected!")

@sio.event
def connect_error(data):
    print("The connection failed!")

@sio.event
def disconnect():
    print("I'm disconnected!")

@sio.on('response')
def on_message(data):
    print(data)

@sio.on('package')
def on_message(data):
    print(data)

@sio.on('fc_telemetry',namespace='/telemetry')
def on_message(data):
    print(data)  
    print(type(data))  
