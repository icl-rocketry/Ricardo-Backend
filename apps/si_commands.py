
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

        self.sio.connect('http://' + host + ':' + str(port) + '/',namespaces=['/','/command','/messages'])  
        self.sio.on('Response',self.on_response_handler,namespace='/command')  

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
        self.sio.emit('send_data',{'data':packet.serialize().hex()},namespace='/command')
    
    #sending commands from user

    #venting arming command with angle of servo argument
    vent_ap = Cmd2ArgumentParser(description='arming of venting and setting angle of servo')
    vent_ap.add_argument('--arm', type=str, help='arming of oxidiser vent', choices=['ARM','DISARM'])
    vent_ap.add_argument('--param', type=int, help='angle of vent valve servo 0-180 degrees')
    vent_ap.add_argument('--getstate', help='request state update',action='store_true')
    
    @with_argparser(vent_ap) 
    def do_vent(self,opts):
        opts.address = 8
        opts.service = 10
        self.component(opts)
        

    fill_ap = Cmd2ArgumentParser(description='arming of filling and setting angle of servo')
    fill_ap.add_argument('--arm', type=str, help='arming of oxidiser fill', choices=['ARM','DISARM'])
    fill_ap.add_argument('--param', type=int, help='angle of fill valve servo 0-180 degrees')
    fill_ap.add_argument('--getstate', help='request state update',action='store_true')
    
    @with_argparser(fill_ap) 
    def do_fill(self,opts):
        opts.address = 12
        opts.service = 10
        self.component(opts)

    hose_vent_ap = Cmd2ArgumentParser(description='arming of hose_venting and setting angle of servo')
    hose_vent_ap.add_argument('--arm', type=str, help='arming of oxidiser hose_vent', choices=['ARM','DISARM'])
    hose_vent_ap.add_argument('--param', type=int, help='angle of hose_vent valve servo 0-180 degrees')
    hose_vent_ap.add_argument('--getstate',  help='request state update',action='store_true')
    
    @with_argparser(hose_vent_ap) 
    def do_hose_vent(self,opts):
        opts.address = 13
        opts.service = 10
        self.component(opts)
    
    retract_ap = Cmd2ArgumentParser(description='arming of retracting and retracting hose')
    retract_ap.add_argument('--arm', type=str, help='arming of oxidiser retract', choices=['ARM','DISARM'])
    retract_ap.add_argument('--param', type=int, help='forward,reverse,stop',choices=[-1,0,1])
    retract_ap.add_argument('--getstate',  help='request state update',action='store_true')
    
    @with_argparser(retract_ap) 
    def do_retract(self,opts):
        opts.address = 13
        opts.service = 10
        try:
            if (opts.param == -1):
                opts.param = 198
            elif(opts.param == 1):
                opts.param = 98
        except KeyError:
            pass

        self.component(opts)
    

    component_ap = Cmd2ArgumentParser()
    component_ap.add_argument('-a','--address',type=int,help='Network Address',required=True)
    component_ap.add_argument('-s','--service',type=int,help='Service ID',required=True)
    component_ap.add_argument('--arm', type=str, help='arming of oxidiser vent', choices=['ARM','DISARM'])
    component_ap.add_argument('--param', type=int, help='angle of vent valve servo 0-180 degrees')
    component_ap.add_argument('--getstate',  help='request state update',action='store_true')

    @with_argparser(component_ap)
    def do_component(self,opts):
        self.component(opts)


    def component(self,opts):

        try:
            if (opts.arm == 'ARM'):
                print('Arming Component')
                self.send_cmd(source=self.source_address,destination=opts.address,command_num=3,arg=0,destination_service=opts.service)
            elif (opts.arm == 'DISARM'):
                print('Disarming Component')
                self.send_cmd(source=self.source_address,destination=opts.address,command_num=4,arg=0,destination_service=opts.service)
        except KeyError:
            pass

        if (opts.param is not None):
            #need to check bounds of param
            self.send_cmd(source=self.source_address,destination=opts.address,command_num=2,arg=opts.param,destination_service=opts.service)

        if (opts.getstate):
            self.send_cmd(source=self.source_address,destination=opts.address,command_num=1,arg=0,destination_service=opts.service)
        
        
    #tank heater arming command with selection of tank and temperature setpoint arguments
    tankheating = Cmd2ArgumentParser(description='selecting tank for heating, arming and setting temperature')
    tankheating.add_argument('tank_num', type=int, help='select tank no. for heating', choices=[1,2])
    tankheating.add_argument('--arm', type=str, help='arming of oxidiser vent', choices=['ARM','DISARM'])
    tankheating.add_argument('--param', type=int, help='angle of vent valve servo 0-180 degrees')
    tankheating.add_argument('--getstate',  help='request state update',action='store_true')
    
    @with_argparser(tankheating) 
    def do_tankheat(self,opts):

        if opts.tank_num==1:
            opts.address = 12
            opts.service = 13
            self.component(opts)
        elif opts.tank_num==2:
            opts.address = 13
            opts.service = 13
            self.component(opts)

    #launch command
    def do_launch(self,opts):
        self.send_cmd(source = self.source_address,destination = 2,command_num=1,arg=0)

    def do_debug(self,opts):
        self.send_cmd(source=self.source_address,destination =2,command_num=100,arg=0)
    
    def do_resetFC(self,opts):
        self.send_cmd(source=self.source_address,destination =2,command_num=2,arg=0)
    
    hitl_ap=Cmd2ArgumentParser()
    hitl_ap.add_argument('--address',type=int,help='Flight Controller Address',default=2)
    hitl_ap.add_argument('--enable',action='store_true',help='Enable Hardware In The Loop Service')
    hitl_ap.add_argument('--disable',action='store_true',help='Disable Hardware In The Loop Service')
    @with_argparser(hitl_ap)
    def do_hitl(self,opts):
        if (opts.enable and opts.disable):
            print("Error!")
            return
        
        if (opts.enable):
            #enter debug mode
            self.send_cmd(source=self.source_address,destination =opts.address,destination_service=2,command_num=100,arg=0)
            time.sleep(0.05)
            #enable hitl
            self.send_cmd(source=self.source_address,destination =opts.address,destination_service=3,command_num=0,arg=0)
            time.sleep(0.05)
            #exit to preflight
            self.send_cmd(source=self.source_address,destination =opts.address,destination_service=2,command_num=101,arg=0)

        if (opts.disable):
            #enable hitl
            self.send_cmd(source=self.source_address,destination =opts.address,destination_service=3,command_num=1,arg=0)

        

    # #abort command
    # def do_a(self,opts):
    #     cmd_id = 2
    #     arg = 0
    #     self.send_cmd(self.source_address,5,cmd_id,arg,destination_service=10)

    def do_sethome(self,opts):
        self.send_cmd(self.source_address,2,4,0)


    #ignition command
    def do_ignite(self,opts):
        self.send_cmd(self.source_address,2,69,0)

    def do_quit(self,opts):
        self.sio.disconnect()
        return True
    
    
    def component_state_handler(self,packet):

        nrc_state_packet = NRCStatePacket.from_bytes(packet)  
        #decode component status
        print(self.__decode_component_state__(nrc_state_packet.state))
        print("VALUE: " + str(nrc_state_packet.value))

        pass

    def __decode_component_state__(self,state):
        binaryString = "{0:b}".format(state)[::-1]#get binary representation and reverse
        return [nrc_component_flag_lookup[idx] for idx in range(len(binaryString)) if binaryString[idx] == '1']
   

ap = argparse.ArgumentParser()
ap.add_argument('-s',"--source",required=False,type=int,default=4,help='Soure Address of packets')
args = vars(ap.parse_args())

if __name__ == "__main__":
    cmd = CmdUI()
    cmd.source_address = args['source']
    sys.exit(cmd.cmdloop())
   
