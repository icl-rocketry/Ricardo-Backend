
import cmd2
import sys
from cmd2.argparse_custom import Cmd2ArgumentParser
from cmd2.decorators import with_argparser
from pylibrnp.defaultpackets import *
from pylibrnp.rnppacket import *
import argparse
import time
import enum

import socketio


class ByteRnpPacket(RnpPacket):
    struct_str='<I'
    size = struct.calcsize(struct_str)
    packet_type = 0

    def __init__(self):
        self.value:int = 0
        super().__init__(['value'],
                         ByteRnpPacket.struct_str,
                         ByteRnpPacket.size,
                         ByteRnpPacket.packet_type)
    
    def __str__(self):
        header_str = self.header.__str__() + '\ns'
        desc_str = str(self.value)
        return header_str


#reference rnp_netman_packets.h
class NETMAN_TYPES(enum.Enum):
    PING_REQ:int = 1
    PING_RES:int = 2
    SET_ADDRESS:int = 3
    SET_ROUTE:int = 4
    SET_TYPE:int = 5
    SET_NOROUTEACTION:int = 6
    SET_ROUTEGEN:int = 7
    SAVE_CONF:int = 8
    RESET_NETMAN:int = 9

#reference rnp_networkmanager.h
class NODE_TYPE(enum.Enum):
    LEAF:int=0
    HUB:int=1

#reference rnp_networkmanager.h
class NOROUTE_ACTION(enum.Enum):
    DUMP:int=0
    BROADCAST:int=1


class NetworkConfigurationTool(cmd2.Cmd):
    sio = socketio.Client(logger=True, engineio_logger=False)

    def __init__(self,host='localhost',port=1337):
        super().__init__(allow_cli_args=False)  

        self.source_address = 4
        self.ping_record = {}
        

        self.sio.connect('http://' + host + ':' + str(port) + '/',namespaces=['/','/command','/messages'])
        self.sio.on('Response',self.on_response_handler,namespace='/command')  

    #setting up socketio client and event handler

    @sio.event
    def connect():
        print("I'm connected!")


    # @sio.on('Response',namespace='/command')
    def on_response_handler(self,data):
        print(data)
        try:
            packet = bytes.fromhex(data['Data'])
            header = RnpHeader.from_bytes(packet)
        except:
            print("Failed to decode header")
            return
        
        print(header)
        if header.packet_type == 2:
            self.ping_response_handler(packet)
            # ping response
            
                
                


            # if header.source_service == 2 and header.packet_type == 100:
            #     #we have a string message packet
            #     packet_body = packet[RnpHeader.size:]
            #     try:
            #         message = packet_body.decode('UTF-8')
            #     except:
            #         message = str(packet_body)
            #     print("Message: " + message)
            # if header.packet_type == 1:
            #     print("got component state")
                

    set_address_ap = Cmd2ArgumentParser()
    set_address_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    set_address_ap.add_argument('-n','--new_address',type=int,help='New Address',required=True)
    @with_argparser(set_address_ap)
    def do_set_address(self,opts):
        print(opts)
        # pass
        packet = ByteRnpPacket()
        packet.value = opts.new_address
        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.SET_ADDRESS.value)

    set_type_ap = Cmd2ArgumentParser()
    set_type_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    set_type_ap.add_argument('-o','--option',type=str,help='Node Type',required = True)
    @with_argparser(set_type_ap)
    def do_set_type(self,opts):
        packet = ByteRnpPacket()
        if opts.option == 'HUB':
            packet.value = NODE_TYPE.HUB.value
        elif opts.option == 'LEAF':
            packet.value = NODE_TYPE.LEAF.value
        else:
            print('Bad Argument')
            return  
        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.SET_TYPE.value)

    set_noroute_ap = Cmd2ArgumentParser()
    set_noroute_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    set_noroute_ap.add_argument('-o','--option',type=str,help='Node Type',required = True)
    @with_argparser(set_noroute_ap)
    def do_set_noroute(self,opts):
        #disabled as need to probably make a custom packet type to send broadcast list aswell otherwise this option
        #makes no sense
        print('disabled as need to probably make a custom packet type to send broadcast list aswell otherwise this option makes no sense')
        return
        packet = ByteRnpPacket()
        if opts.type == 'DUMP':
            packet.value = NODE_TYPE.HUB
        elif opts.type == 'LEAF':
            packet.value = NODE_TYPE.LEAF
        else:
            print('Bad Argument')
            return  
        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.SET_NOROUTEACTION.value)

    set_routegen_ap = Cmd2ArgumentParser()
    set_routegen_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    set_routegen_ap.add_argument('-e','--enable',help='Enable Automatic Route Generation',action='store_true')
    @with_argparser(set_routegen_ap)
    def do_set_routegen(self,opts):
        packet = ByteRnpPacket()
        if opts.enable:
            packet.value = 1
        else:
            packet.value = 0

        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.SET_ROUTEGEN.value)

    set_save_conf_ap = Cmd2ArgumentParser()
    set_save_conf_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    @with_argparser(set_save_conf_ap)
    def do_save_conf(self,opts):
        packet = ByteRnpPacket()
        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.SAVE_CONF.value)


    set_reset_ap = Cmd2ArgumentParser()
    set_reset_ap.add_argument('-a','--current_address',type=int,help='Node Current Address',default=0)
    @with_argparser(set_reset_ap)
    def do_reset(self,opts):
        packet = ByteRnpPacket()
        self.send_packet(packet,destination=opts.current_address,packet_type=NETMAN_TYPES.RESET_NETMAN.value)


    @sio.event
    def connect_error(data):
        print("The connection failed!")

    @sio.event
    def disconnect():
        print("I'm disconnected!")

    #method for serializing and sending command and its argument
    def send_packet(self,packet,destination,source=None,destination_service = 1,source_service  = 2,packet_type = 0):
        packet.header.source_service = source_service
        packet.header.destination_service = destination_service

        if (source is None):
            source = self.source_address

        packet.header.source = int(source)
        packet.header.destination = int(destination)
        packet.header.packet_type = int(packet_type)
        self.sio.emit('send_data',{'data':packet.serialize().hex()},namespace='/command')
    



    ping_ap = Cmd2ArgumentParser(description = 'ping component')
    ping_ap.add_argument('-a','--address',type=int,help='address to ping',required= True)
    ping_ap.add_argument('-c','--continuous',help='send ping continoiusly',action='store_true')
    ping_ap.add_argument('-t','--timeout',help='set packet timeout in milliseconds',type=int,default=2000)

    @with_argparser(ping_ap)
    def do_ping(self,opts):
        try:
            while True:
                if opts.address in self.ping_record.keys():
                    ping_status = self.ping_record[opts.address]
                    #check for timeout
                    if (time.time() - ping_status['time_sent'] > opts.timeout/1000):
                        if (ping_status['time_received'] is None):
                            print("Ping to " + str(opts.address) + " timed out")
                        self.send_ping(opts.address)
                    
                else:
                    self.send_ping(opts.address)
                
                if not opts.continuous:
                    break

            pass
        except KeyboardInterrupt:
            return
            
        
        return
    

    def send_ping(self,destination):
        
        try:
            ping_status = self.ping_record[destination]
            ping_status['sent'] += 1
            ping_status['time_sent'] = time.time()
        except KeyError:
            self.ping_record[destination] = {
                'time_sent':time.time(),
                'time_received':None,
                'sent':1,
                'received':0,
                'loss_rate':0,
                'average_latency':0
            }

        pingpacket = ByteRnpPacket()
        self.send_packet(pingpacket,destination=destination,packet_type=NETMAN_TYPES.PING_REQ.value)



        

    def ping_response_handler(self,packet_data):
        #decode packet
        ping_response = ByteRnpPacket.from_bytes(packet_data)
        try:
            ping_status = self.ping_record[ping_response.header.source]
            ping_status['time_received'] = time.time()
            latency = ping_status['time_received'] - ping_status['time_sent']
            average_latency = ((ping_status['average_latency'] * ping_status['received']) + latency) /(ping_status['received']+1)
            ping_status['average_latency'] = average_latency
            ping_status['received'] += 1
            ping_status['loss_rate'] = (1-(ping_status['received']/ping_status['sent'])) * 100

            print('Ping Received from:' + str(ping_response.header.source) + ' latency: ' + str(latency) + ' average latency:' + str(average_latency) + ' sent' + str(ping_status['sent']) + ' received:' + str(ping_status['received']) + ' loss:' + str(ping_status['loss_rate']))
               
        except KeyError:
            print("Received Unkown ping response -> cant find " + str(ping_response.header.source) + " in ping record")


    # def sigint_handler(self,p1=None,p2=None):
    #     self.sio.disconnect()
    #     sys.exit(0)

    def do_quit(self,opts):
        self.sio.disconnect()
        return True
    
    

ap = argparse.ArgumentParser()
ap.add_argument('-s',"--source",required=False,type=int,default=4,help='Soure Address of packets')

args = vars(ap.parse_args())


if __name__ == "__main__":
    netconf = NetworkConfigurationTool()
    netconf.source_address = args['source']
    netconf.cmdloop()
