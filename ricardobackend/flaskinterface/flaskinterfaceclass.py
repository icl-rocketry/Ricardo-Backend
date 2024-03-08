
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


    def __init__(self):
        # APP INITIALIZATION

        # flask app 
        self.app = Flask(__name__)
        self.app.register_blueprint(command_webui_bp, url_prefix="/command_ui")
        self.app.register_blueprint(telemetry_webui_bp, url_prefix="/telemetry_ui")
        self.app.register_blueprint(taskhandler_webui_bp, url_prefix="/taskhandler_ui")


        self.app.config["SECRET_KEY"] = "secret!"
        self.app.config['DEBUG'] = False
        
        # socketio app
        self.socketio = SocketIO(app,cors_allowed_origins="*",async_mode='eventlet',logger=False)
        self.socketio_clients = []
        #flask rest api variables
        rest_response_queue_maxsize = 100
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

        # # misc
        # prev_time = 0
        # updateTimePeriod = 0.01 #in seconds

        pass