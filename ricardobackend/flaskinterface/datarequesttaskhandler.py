

# import socketio
import json
import simplejson #needed to handle NaNs... smh

import time
from pylibrnp import rnppacket
from pylibrnp import defaultpackets
from pylibrnp import dynamic_rnp_packet_generator as drpg
from pylibrnp import bitfield_decoder
import csv
import sys
import signal
import copy
from datetime import datetime
import multiprocessing as mp
from queue import Full,Empty
import os




MS_TO_NS = 1e6
class DataRequestTask():
    def __init__(self,jsonconfig):
        
        self.config = None

        self.packet_class = None #class type representing incomming data packet
        self.bitfield_decoder_list = [] #bitfield decoders to decode system status strings

        self.updateConfig(jsonconfig)

        self.connectionTimeout = 5000 #in ms
        self.lastReceivedTime = 0

        
        self.fileName = "Logs/"+self.config['task_name']+"_"+datetime.now().strftime("%d_%m_%y_%H_%M_%S_%f")+'.csv'

        os.makedirs(os.path.dirname(self.fileName), exist_ok=True)

        self.logfile = open(self.fileName,'x')

        logfile_header = ["BackendTime"] + self.packet_class().packetvars
        self.csv_writer = csv.DictWriter(self.logfile,fieldnames=logfile_header)
        self.csv_writer.writeheader()

        self.prevUpdateTime = 0
    
    def updateConfig(self,jsonconfig):
        #deep copy here 
        self.config=copy.deepcopy(jsonconfig)
        self.config['rxCounter'] = 0
        self.config['txCounter'] = 0
        self.config['connected'] = True
        self.config['lastReceivedPacket'] = ""
        #generate dynamic type and store type
        self.packet_class = drpg.DynamicRnpPacketGenerator('anon_packettype',self.config['packet_descriptor']).getClass()
        
        self.bitfield_decoder_list = copy.deepcopy(jsonconfig.get('bitfield_decoders',[]))
        for decoder in self.bitfield_decoder_list:
            try:
                decoder['decoder'] = bitfield_decoder.BitfieldDecoder(decoder['flags'])
            except KeyError:
                print('[Data Task Request Handler] Bad Config, ignoring entry' + decoder)
                continue
        

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
                command_packet.header.source_service = requestConfig.get('source_service',0) #this is not too important
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

        try:
            deserialized_packet = self.packet_class.from_bytes(data)
        except rnppacket.DeserializationError as e:
            print('[ERROR - Data Task Request Handler] - received badly formed packet: ' + str(e))
            return None
        
        if self.config['logger']:
            data_row = {"BackendTime":time.time()*1000,**deserialized_packet.getData()}
            self.csv_writer.writerow(data_row)
        
        packetData = deserialized_packet.getData()
        #decode bitfields if there are any
        for decoder in self.bitfield_decoder_list:

            variableName = decoder.get('variable_name',None)
            if variableName is None:
                continue
            
            if variableName in packetData.keys():
                print('[ERROR - Data Task Request Handler] bitfield variable name already exists in decoded packet data, skipping...')
                continue
            
            try:
                packetData[variableName] = decoder['decoder'].decode(int(packetData[decoder['bitfield']]))
            except KeyError:
                 print('[ERROR - Data Task Request Handler] key not found, skipping...')

        return packetData


    def __exit__(self,*args):
        self.logfile.close()

    

class DataRequestTaskHandler():


    def __init__(self,sio_instance,sendQ=None,receiveQ = None,socketiohost=None,socketioport=None,prefix:str = "flaskinterface",verbose:bool=False):
        # self.r = redis.Redis(redishost,redisport)
        if sendQ is None or receiveQ is None:
            raise Exception('No send queue or receive queue provided')

        self.sendQ:mp.Queue = sendQ
        self.receiveQ:mp.Queue = receiveQ

        self.identifier = {"prefix":prefix,"process_id":'DTRH'}

        self.config_filename = 'Config/DataRequestTaskConfig.json'
        
        self.task_container = {} #{task_name:task_object}

        # assign functions to events
        self.sio = sio_instance

        self.verbose=verbose

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
        

    def on_save_handler_config(self,data):

        if self.task_container is False:
            print("No Tasks, Saving empty json")
            handler_config = {}
        else:
            handler_config = [task.config for task in self.task_container.values()]
        with open(self.config_filename,'w',encoding='utf-8') as file:
            file.write(json.dumps(handler_config,indent=1))
    
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
        if decodedData is None:
            return
        #publish to socketio
        #use simplejson to dump json as string so that NaNs are converted to null
        self.sio.emit(task_id,simplejson.dumps(decodedData,ignore_nan=True),namespace='/telemetry')
        #publish to redis depreceated


        
    def __sendPacketFunction__(self,packet,task_id):
        #construct send data using deepcopy to prevent reference to self.identifier

        send_data = copy.deepcopy({
            "data":packet.serialize().hex(),
            "identifier":self.identifier
        })

        send_data['identifier']['task_id'] = task_id

        try:
            self.sendQ.put_nowait(send_data)
        except Full:
            print("[Data Task Request Handler] Send Queue Full!")
    
    def __checkReceiveQueue__(self):

        try:
            item = self.receiveQ.get_nowait()
            identifier = item['identifier']
            task_id = identifier['task_id']
            if task_id in self.task_container.keys():
                responseData:bytes = item['data']
                self.publish_new_data(responseData,task_id)
            else:
                #task id no longer active so dump received data
                print('dumping')
                pass

        except Empty:
            pass


    def __exitHandler__(self,sig=None,frame=None):
        self.run=False
        sys.exit(0)

        