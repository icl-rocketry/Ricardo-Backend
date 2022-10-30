
from cgitb import lookup
from dataclasses import field
from queue import Empty
import threading
import redis
import socketio
import json
import time
from ...pylibrnp import defaultpackets
from ...pylibrnp import dynamic_rnp_packet_generator as drpg
import csv
import sys
import signal

class DataRequestTask():
    def __init__(self,jsonconfig):
        
        self.config = None
        self.packet_class = None #class type representing incomming data packet
        self.updateConfig(jsonconfig)

        self.connectionTimeout = 5000 #in ms
        self.lastReceivedTime = 0

        try:
            self.logfile = open(self.config['task_name']+'.csv','x')
            newFile = True
        except FileExistsError:
            self.logfile = open(self.config['task_name']+'.csv','a')
        self.csv_writer = csv.DictWriter(self.logfile,fieldnames=self.packet_class.packetvars)

        if newFile:
            self.csv_writer.writeheader()

        self.prevUpdateTime = 0
    
    def updateConfig(self,jsonconfig):
        self.config=jsonconfig
        self.config['rxCounter'] = 0
        self.config['txCounter'] = 0
        self.config['connected'] = True
        self.config['lastReceivedPacket'] = ""
        #generate dynamic type and store type
        self.packet_class = drpg.DynamicRnpPacketGenerator(self.config['packet_descriptor']).getClass()

    def requestUpdate(self):

        if self.config['running']:

            if (time.time_ns() - self.lastReceivedTime > (self.connectionTimeout*1000)):
                self.config['connected'] = False

            if (time.time_ns() - self.prevUpdateTime > (self.config["poll_delta"]*1000)):
                command_packet = defaultpackets.SimpleCommandPacket(command = self.config['command_id'],arg=self.config['request_config']['command_arg'])
                command_packet.header.source = self.config['request_config']['source']
                command_packet.header.destination = self.config['request_config']['destination']
                command_packet.header.source_service = 2 #this is not too important
                command_packet.header.destination_service = self.config['request_config']['destination_service']
                command_packet.header.packet_type = 0 #command packet type is always zero
                self.prevUpdateTime = time.time_ns()
                self.config['txCounter'] += 1
                return command_packet

        return None

    def decodeData(self,data):
        #update connection state varaibles
        self.config['rxCounter'] += 1
        self.lastReceivedTime = time.time_ns()
        self.config['lastReceivedPacket'] = data
        self.config['connected'] = True

        deserialized_packet = self.packet_class.from_bytes(data)
        if self.config['logger']:
            self.csv_writer.writerow(deserialized_packet.getData())
        return deserialized_packet.getData()


    def __exit__(self,*args):
        self.logfile.close()

    


class DataRequestTaskHandler():

    sio = socketio.Client()

    def __init__(self,redishost,redisport,socketiohost,socketioport):
        self.r = redis.Redis(redishost,redisport)
        self.client_id_prefix = "LOCAL:DATAREQUESTHANDLER:"
        
        self.task_container = {} #{task_name:task_object}

        self.sio.connect('http://' + socketiohost + ':' + str(socketioport) + '/',namespaces=['/','/telemetry','/data_request_handler'])
        # assign functions to events
        self.sio.on('getRunningTasks',self.on_get_running_tasks,namespace='/data_request_handler')
        self.sio.on('newTaskConfig',self.on_new_task_config,namespace='/data_request_handler')
        self.sio.on('deleteTaskConfig',self.on_delete_task_config,namespace='/data_request_handler')
        self.sio.on('saveHandlerConfig',self.on_save_handler_config,namespace='/data_request_handler')
        self.sio.on('clearTasks',self.on_clear_tasks,namespace='/data_request_handler')

        self.handler_config = []
        self.run = True
        signal.signal(signal.SIGINT,self.__exitHandler__)
        signal.signal(signal.SIGNTERM,self.__exitHandler__)


    def on_get_running_tasks(self):
        """Returns the current running tasks within the data request task handler as a json"""
        #concatenate all task configs into single dict and emit to all clients
        running_tasks = [task.config for task in self.task_container.values()]
        self.sio.emit('runningTasks',running_tasks,namespace='/data_request_handler')
        
      
    def on_new_task_config(self,data):
        """Adds a new task to the config to reques new data"""
        #if already exists, delete old task and spin up new one
        task_id = data["task_name"]
        if task_id in self.task_container.keys():
            self.task_container[task_id].updateConfig(data)
        else:
            self.task_container[task_id] = DataRequestTask(data)
    
    def on_delete_task_config(self,data):
        task_id = data['task_name']
        self.task_container.pop(task_id) #delete that task
        

    def on_save_handler_config(self):

        if self.handler_config is False:
            print("No Config to save!")
            return

        with open('DataRequestTaskConfig.json','w',encoding='utf-8') as file:
            json.dump(self.handler_config,file)
    
    def on_clear_tasks(self):
        self.handler_config = []
        


    def mainloop(self):
        while self.run:
            for key,task in self.task_container.items():
                request_packet = task.requestUpdate() 
                if request_packet is not None:
                    self.__sendPacketFunction__(request_packet,task.config['task_name'])
            self.__checkReceiveQueue__()
    
    def publish_new_data(self,data,task_id):
        task = self.task_container[task_id]
        decodedData = task.decodeData(data)
        #add prefix to new json
        prefixedData = {decodedData[task_id+":"+key]:value for key,value in decodedData.items()}

        
    def __sendPacketFunction__(self,packet,task_id):
        send_data = {
            "data":packet.serialize().hex(),
            "clientid":self.client_id_prefix + task_id
        }
        self.r.lpush("SendQueue",json.dumps(send_data))
    
    def __checkReceiveQueue__(self):
        lookup_string = 'ReceiveQueue:'+self.client_id_prefix+"*"
        keylist = list(self.r.scan_iter(lookup_string,1)) #find keys with the prefix 
        if keylist: #check we got keys
            key = keylist[0] #only process 1 key at a time
            key_string:str = bytes(key).decode("UTF-8")
            task_id = key_string[len(lookup_string):]

            if task_id in self.task_container.keys():
                self.r.persist(key) #remove key timeout
                responseData:bytes = self.r.rpop(key)
                self.publish_new_data(responseData,task_id)

            else:
                self.r.delete(key)#delete the whole receive queue as task is no longer active   
        

    def __exitHandler__(self,sig=None,frame=None):
        self.run=False
        self.sio.disconnect()
        sys.exit(0)