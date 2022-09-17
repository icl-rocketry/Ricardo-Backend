import cmd2
from cmd2.argparse_custom import Cmd2ArgumentParser
from cmd2.decorators import with_argparser
from pylibrnp.defaultpackets import *
from pylibrnp.rnppacket import *

import socketio





class CmdUI(cmd2.Cmd):

    sio = socketio.Client(logger=True, engineio_logger=False)

    def __init__(self,host='localhost',port=1337):
        super().__init__(allow_cli_args=False)  
        

        self.sio.connect('http://' + host + ':' + str(port) + '/',namespaces=['/','/command','/messages'])  

    #setting up socketio client and event handler

    @sio.event
    def connect():
        print("I'm connected!")


    @sio.on('Response',namespace='/command')
    def on_response_handler(data):
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

        except:
            print("Failed to decode header")




    @sio.event
    def connect_error(data):
        print("The connection failed!")

    @sio.event
    def disconnect():
        print("I'm disconnected!")

    #method for serializing and sending command and its argument
    def send_cmd(self,source, destination, command_num, arg,destination_service = 2,source_service  = 2):
        cmd_packet : SimpleCommandPacket = SimpleCommandPacket(command = int(command_num), arg = int(arg))
        cmd_packet.header.source_service = source_service
        cmd_packet.header.destination_service = destination_service
        cmd_packet.header.source = int(source)
        cmd_packet.header.destination = int(destination)
        cmd_packet.header.packet_type = 0
        self.sio.emit('send_data',{'data':cmd_packet.serialize().hex()},namespace='/command')
    



    #sending commands from user

    #venting arming command with angle of servo argument
    venting = Cmd2ArgumentParser(description='arming of venting and setting angle of servo')
    venting.add_argument('--arming', type=str, help='arming of oxidiser vent', choices=['a','d'])
    venting.add_argument('--angle', type=int, help='angle of vent valve servo 0-180 degrees', choices=range(0, 180))
    
    @with_argparser(venting) 
    def do_vent(self,opts):
        
        print(opts.arming)
        if (opts.arming is 'a'):
            print('do arming')


        if opts.arming.a:
            command_num = 1 #doesnt mean anything
        if opts.arming.d:
            command_num = 2

        arg = opts.angle
        
        self.send_cmd(1, 1, command_num, arg)




    #tank heater arming command with selection of tank and temperature setpoint arguments
    tankheating = Cmd2ArgumentParser(description='selecting tank for heating, arming and setting temperature')
    tankheating.add_argument('tank_num', type=int, help='select tank no. for heating', choices=[1,2])
    tankheating.add_argument('--arming', type=str, help='arming of tank heater', choices=['a','d'])
    tankheating.add_argument('--setpoint', type=int, help='temperature setpoint')
    
    @with_argparser(tankheating) 
    def do_tankheat(self,opts):

        if opts.tank_num==1:
            if opts.arming.a:
                command_num = 1
            if opts.arming.d:
                command_num = 2
            arg = opts.setpoint    

        if opts.tank_num==2:
            if opts.arming.a:
                command_num = 3
            if opts.arming.d:
                command_num = 4
            arg = opts.setpoint
        

        self.send_cmd(1, 1, command_num, arg)




    # #filling arming command with angle argument
    # filling = Cmd2ArgumentParser(description='arming of filling and setting angle of servo')
    # filling.add_argument('--arming', type=str, help='arming of oxidiser filling', choices=['a','d'])
    # filling.add_argument('--angle', type=int, help='angle of fill valve servo 0-180 degrees', choices=range(0,180))
    
    # @with_argparser(filling) 
    # def do_fill(self,opts):
    #     if opts.arming.arm:
    #         command_num = 1
    #     if opts.arming.disarm:
    #         command_num = 2

    #     arg = opts.angle

    #     self.send_cmd(1, 1, command_num, arg)




    #launch command
    def do_launch(self,opts):

        self.send_cmd(4,2,1,0)




    #abort command
    def do_a(self,opts):
        cmd_id = 2
        arg = 0
        self.send_cmd(4,5,cmd_id,arg,destination_service=10)




    #ignition command
    def do_ignite(self,opts):
        self.send_cmd(4,2,69,0)

    # #retract QD command
    # def do_retract(self):

    #     command_num = 1

    #     arg = 0

    #     self.send_cmd(1,1,command_num,arg)



if __name__ == "__main__":
    cmd = CmdUI()
    cmd.cmdloop()
