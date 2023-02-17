

import threading
import redis
# import socketio
import json
import time
from pylibrnp import defaultpackets
from pylibrnp import dynamic_rnp_packet_generator as drpg
import csv
import sys
import signal
from datetime import datetime


MS_TO_NS = 1e6
class DataRequestTask():
    def __init__(self,jsonconfig):
        
        self.config = None
        self.packet_class = None #class type representing incomming data packet
        self.updateConfig(jsonconfig)

        self.connectionTimeout = 5000 #in ms
        self.lastReceivedTime = 0

        
        self.fileName = "Logs/"+self.config['task_name']+"_"+datetime.now().strftime("%d_%m_%y_%H_%M_%S_%f")+'.csv'

        newFile=False


        self.logfile = open(self.fileName,'x')

        self.csv_writer = csv.DictWriter(self.logfile,fieldnames=self.packet_class().packetvars)
        self.csv_writer.writeheader()

        self.prevUpdateTime = 0
    
    def updateConfig(self,jsonconfig):
        self.config=jsonconfig
        self.config['rxCounter'] = 0
        self.config['txCounter'] = 0
        self.config['connected'] = True
        self.config['lastReceivedPacket'] = ""
        #generate dynamic type and store type
        self.packet_class = drpg.DynamicRnpPacketGenerator('anon_packettype',self.config['packet_descriptor']).getClass()

    def requestUpdate(self):

        if self.config['running']:
    
            if (time.time_ns() - self.lastReceivedTime > (self.connectionTimeout*MS_TO_NS)): #if connection timed out
                self.config['connected'] = False

            if (self.config.get('receiveOnly',False)):#receive only mode
                return None

            if (time.time_ns() - self.prevUpdateTime > (self.config["poll_delta"]*MS_TO_NS)):
                
                requestConfig = self.config.get('request_config',None) #check a request config has been provided
                if requestConfig is None:
                    print("Error No Request Config")
                    return None
                
                command_packet = defaultpackets.SimpleCommandPacket(command = requestConfig['command_id'],arg=requestConfig['command_arg'])
                command_packet.header.source = requestConfig['source']
                command_packet.header.destination = requestConfig['destination']
                command_packet.header.source_service = 2 #this is not too important
                command_packet.header.destination_service = requestConfig['destination_service']
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


    def __init__(self,sio_instance,redishost,redisport,socketiohost=None,socketioport=None):
        self.r = redis.Redis(redishost,redisport)
        self.client_id_prefix = "LOCAL:DATAREQUESTHANDLER:"
        self.config_filename = 'Config/DataRequestTaskConfig.json'
        
        self.task_container = {} #{task_name:task_object}

        # assign functions to events
        self.sio = sio_instance

        self.sio.on_event('getRunningTasks',self.on_get_running_tasks,namespace='/data_request_handler')
        self.sio.on_event('newTaskConfig',self.on_new_task_config,namespace='/data_request_handler')
        self.sio.on_event('deleteTaskConfig',self.on_delete_task_config,namespace='/data_request_handler')
        self.sio.on_event('saveHandlerConfig',self.on_save_handler_config,namespace='/data_request_handler')
        self.sio.on_event('clearTasks',self.on_clear_tasks,namespace='/data_request_handler')

        
        self.run = True
        signal.signal(signal.SIGINT,self.__exitHandler__)
        signal.signal(signal.SIGTERM,self.__exitHandler__)
        self.load_handler_config() #load handler config if it exists


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
        self.task_container.pop(task_id).__exit__() #call destructor and delete that task
        

    def on_save_handler_config(self):

        if self.task_container is False:
            print("No Tasks, Saving empty json")
            handler_config = {}
        else:
            handler_config = [task.config for task in self.task_container.values()]
        with open(self.config_filename,'w',encoding='utf-8') as file:
            json.dump(handler_config,file)
    
    def load_handler_config(self):
        try:
            with open(self.config_filename,'r',encoding='utf-8') as file:
                try:
                    handler_config = json.load(file)
                    if not handler_config:
                        print("Empty Json Config")
                        return
                    for config in handler_config:
                        if config.get('autostart',0) is True:
                            config['running'] = True
                        else:
                            config['running'] = False
                        self.on_new_task_config(config) 
                        #generate new tasks
                except json.JSONDecodeError:
                    print("Error opening config file!")
                    return
        except FileNotFoundError as e:
            print(e)
            print('No Config Found!')
            return
        

    def on_clear_tasks(self):
        #remove all tasks and call destructor on all
        task_ids = self.task_container.keys()
        [self.task_container.pop(task_id).__exit__() for task_id in task_ids] 



    def mainloop(self):
        while self.run:
            for task_id,task in self.task_container.items():    
                request_packet = task.requestUpdate() 
                if request_packet is not None:
                    self.__sendPacketFunction__(request_packet,task_id)
            self.__checkReceiveQueue__()
            self.sio.sleep(0.005)
    
    def publish_new_data(self,data,task_id):
        task = self.task_container[task_id]
        decodedData = task.decodeData(data)
        #publish to socketio
        self.sio.emit(task_id,json.dumps(decodedData),namespace='/telemetry')
        #publish to redis -> note the prefix "telemetry:" which is being used to namepsace the key 
        #to replicate how the data is served in socketio 
        self.r.set("telemetry:"+task_id,json.dumps(decodedData))


        
    def __sendPacketFunction__(self,packet,task_id):
        send_data = {
            "data":packet.serialize().hex(),
            "clientid":self.client_id_prefix + task_id
        }
        self.r.lpush("SendQueue",json.dumps(send_data))
    
    def __checkReceiveQueue__(self):
        keylist = list(self.r.scan_iter('ReceiveQueue:'+self.client_id_prefix+"*",1)) #find keys with the prefix 
        if keylist: #check we got keys
           
            key = keylist[0] #only process 1 key at a time
            key_string:str = bytes(key).decode("UTF-8")
            task_id = key_string[len('ReceiveQueue:'+self.client_id_prefix):]
            if task_id in self.task_container.keys():
                
                self.r.persist(key) #remove key timeout
                responseData:bytes = self.r.rpop(key)
                self.publish_new_data(responseData,task_id)

            else:
                self.r.delete(key)#delete the whole receive queue as task is no longer active   
        

    def __exitHandler__(self,sig=None,frame=None):
        self.run=False
        sys.exit(0)

        