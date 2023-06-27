
import cmd2
from cmd2.argparse_custom import Cmd2ArgumentParser
from cmd2.decorators import with_argparser
from pylibrnp.defaultpackets import *
from pylibrnp.rnppacket import *
import sys
import time
import argparse

import socketio

nrc_component_flag_lookup = [([0,0])]*16
nrc_component_flag_lookup[0] = ['INFO','NOMINAL']
nrc_component_flag_lookup[1] = ['INFO','DISARMED']
nrc_component_flag_lookup[2] = ['ERROR','NORESPONSE']
nrc_component_flag_lookup[3] = ['ERROR','CONTINUITY']
nrc_component_flag_lookup[4] = ['ERROR','PINS']
nrc_component_flag_lookup[5] = ['ERROR','I2C']
nrc_component_flag_lookup[6] = ['ERROR','ERROR']

class NRCStatePacket(RnpPacket):
    struct_str='<Hl'
    size = struct.calcsize(struct_str)
    packet_type = 1

    def __init__(self):
        self.state:int=0
        self.value:int=0
        super().__init__(['state','value'],
                         NRCStatePacket.struct_str,
                         NRCStatePacket.size,
                         NRCStatePacket.packet_type)
    
    def __str__(self):
        header_str = self.header.__str__() + '\n'
        desc_str = "STATE: " + str(self.state) + "\nVALUE: " + str(self.value)
        return header_str+desc_str

class CmdUI(cmd2.Cmd):

    sio = socketio.Client(logger=False, engineio_logger=False)

    def __init__(self,host='localhost',port=1337):
        super().__init__(allow_cli_args=False)  

        self.source_address = 4
        self.component_state_request_record = {}

        self.sio.connect('http://' + host + ':' + str(port) + '/',namespaces=['/','/packet','/messages'])  
        self.sio.on('Response',self.on_response_handler,namespace='/packet')  

    #setting up socketio client and event handler

    @sio.event
    def connect():
        print("I'm connected!")

    def on_response_handler(self,data):
        print(data)
        try:
            packet = bytes.fromhex(data['Data'])
            header = RnpHeader.from_bytes(packet)
            print(header)
            if header.source_service == 2 and header.packet_type == 100:
                #we have a string message packet
                packet_body = packet[RnpHeader.size:]
                try:
                    message = packet_body.decode('UTF-8')
                except:
                    message = str(packet_body)
                print("Message: " + message)
            if header.packet_type == 1:
                print("got component state")
                self.component_state_handler(packet)
                

        except:
            print("Failed to decode header")




    @sio.event
    def connect_error(data):
        print("The connection failed!")

    @sio.event
    def disconnect():
        print("I'm disconnected!")

    cmd_ap = Cmd2ArgumentParser(description='send command')
    cmd_ap.add_argument('--source',type=int,default=1)
    cmd_ap.add_argument('--destination',type=int,required=True)
    cmd_ap.add_argument('--source_service',type=int,default=2)
    cmd_ap.add_argument('--destination_service',type=int,default=2)
    cmd_ap.add_argument('--command_id',type=int,required=True)
    cmd_ap.add_argument('--arg',type=int,default=0)
    def do_send_cmd(self,opts):
        self.send_cmd(source=opts.source,destination=opts.destination,command_num=opts.command_id,arg=opts.arg,destination_service=opts.destination_service,source_service=opts.source_service)

    #method for serializing and sending command and its argument
    def send_cmd(self,source, destination, command_num, arg,destination_service = 2,source_service  = 2):
        cmd_packet : SimpleCommandPacket = SimpleCommandPacket(command = int(command_num), arg = int(arg))
        self.send_packet(cmd_packet,destination=destination,source=source,destination_service=destination_service,source_service=source_service,packet_type=0)
    
    def send_packet(self,packet,destination,source=None,destination_service = 1,source_service  = 2,packet_type = 0):
        packet.header.source_service = source_service
        packet.header.destination_service = destination_service

        if (source is None):
            source = self.source_address

        packet.header.source = int(source)
        packet.header.destination = int(destination)
        packet.header.packet_type = int(packet_type)
        self.sio.emit('send_data',{'data':packet.serialize().hex()},namespace='/packet')
    
    #sending commands from user

    startflood_ap = Cmd2ArgumentParser()
    startflood_ap.add_argument('-dest','--destinations', nargs = '+', help = 'list of destinations, separated by a space', required = True)
    startflood_ap.add_argument('--rate',type=int,default = 500, help = 'time delay between transmissions in microseconds' , required = False)
    startflood_ap.add_argument('--command',type=int, help = 'command number', default = 250, required = False)
    startflood_ap.add_argument('--destination_service',type=int,default = 2, required = False)
    startflood_ap.add_argument('--source_service',type=int,default = 2, required = False)

    @with_argparser(startflood_ap)
    def do_startflood(self,opts):
        self.rate = opts.rate / 1000000;
        global flood_run
        flood_run = True
        while(flood_run):
            for tempdest in opts.destinations :
                self.send_cmd(1,tempdest, opts.command, opts.destination_service,opts.source_service)
                time.sleep(self.rate)
    
    def do_stop(self,opts):
        global flood_run
        flood_run = False

ap = argparse.ArgumentParser()
ap.add_argument('-s',"--source",required=False,type=int,default=4,help='Soure Address of packets')
args = vars(ap.parse_args())

if __name__ == "__main__":
    cmd = CmdUI()
    cmd.source_address = args['source']
    sys.exit(cmd.cmdloop())
   
