
from concurrent.futures import thread
from pylibrnp.defaultpackets import processedsensorpacket
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
import threading


flight_sensor_board_address = 7
ground_sensor_board_address = 16

sensor_update_run = False

def get_sensor_update_thread(sio,source_address,dt):
    global sensor_update_run
    while sensor_update_run:
        get_sensor_values = SimpleCommandPacket(command=8,arg=0)
        get_sensor_values.header.source_service = 10
        get_sensor_values.header.destination_service = 2
        get_sensor_values.header.source = int(source_address)
        get_sensor_values.header.destination = flight_sensor_board_address

        sio.emit('send_data',{'data':get_sensor_values.serialize().hex()},namespace='/command')
        
        get_sensor_values.header.destination = ground_sensor_board_address

        sio.emit('send_data',{'data':get_sensor_values.serialize().hex()},namespace='/command')
        
        time.sleep(dt/1000)
    print('process killed')


class SI_Sensor_View(cmd2.Cmd):
    sio = socketio.Client(logger=False, engineio_logger=False)

    def __init__(self,host='localhost',port=1337):
        super().__init__(allow_cli_args=False)  

        self.source_address = 4
        

        self.thread_handle = None
        self.sensor_data = {}
        

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
        if header.packet_type == 103 and header.destination_service==10:
            sensor_packet = processedsensorpacket.from_bytes(packet)
            if (header.source == ground_sensor_board_address):
                self.sensor_data["load"] = sensor_packet.ch0sens
                self.sensor_data["temp1"] = sensor_packet.ch2sens
                self.sensor_data["temp2"] = sensor_packet.ch3sens
                self.sensor_data["hose_p"] = sensor_packet.ch6sens
                self.sensor_data["fill_p"] = sensor_packet.ch9sens

            if (header.source == flight_sensor_board_address):
                self.sensor_data["temp3"] = sensor_packet.ch3sens
                self.sensor_data["cham_p"] = sensor_packet.ch6sens
                self.sensor_data["tank_p"] = sensor_packet.ch9sens

        print(self.sensor_data) 
            
            

    start_ap = Cmd2ArgumentParser()
    start_ap.add_argument('rate',type=int)   
    @with_argparser(start_ap)
    def do_start(self,opts):
        global sensor_update_run
        sensor_update_run = False
        time.sleep(0.1)
        sensor_update_run = True
        self.thread_handle = threading.Thread(target = get_sensor_update_thread,args = (self.sio,self.source_address,opts.rate)).start()

    def do_stop(self,opts):
        global sensor_update_run
        sensor_update_run= False

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
    
    
    def do_quit(self,opts):
        self.sio.disconnect()
        return True
    
    

ap = argparse.ArgumentParser()
ap.add_argument('-s',"--source",required=False,type=int,default=4,help='Soure Address of packets')

args = vars(ap.parse_args())


if __name__ == "__main__":
    si_sensor_view = SI_Sensor_View()
    si_sensor_view.source_address = args['source']
    si_sensor_view.cmdloop()
