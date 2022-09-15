import cmd2
from cmd2.argparse_custom import Cmd2ArgumentParser
from cmd2.decorators import with_argparser
from pylibrnp.defaultpackets import *

import socketio





class CmdUI(cmd2.Cmd):



    def __init__(self):
        super().__init__(allow_cli_args=False)    



    #setting up socketio client and event handler
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event
    def connect():
        print("I'm connected!")

    @sio.event
    def connect_error(data):
        print("The connection failed!")

    @sio.event
    def disconnect():
        print("I'm disconnected!")



    #method for serializing and sending command and its argument
    def send_cmd(source, destination, command_num, arg):
        cmd_packet : SimpleCommandPacket = SimpleCommandPacket(command = int(command_num), arg = int(arg))
        cmd_packet.header.destination_service = 2 #Note on old fw this will be 1
        cmd_packet.header.source = int(source)
        cmd_packet.header.destination = int(destination)

        CmdUI.sio.emit('Command',{cmd_packet.serialize()})
    



    #sending commands from user

    #venting arming command with angle of servo argument
    venting = Cmd2ArgumentParser(description='arming of venting and setting angle of servo')
    venting.add_argument('--arming', type=str, help='arming of oxidiser vent', choices=['a','d'])
    venting.add_argument('--angle', type=int, help='angle of vent valve servo 0-180 degrees', choices=range(0, 180))
    
    @with_argparser(venting) 
    def do_vent(self,opts):
        
        if opts.arming.a:
            command_num = 1 #doesnt mean anything
        if opts.arming.d:
            command_num = 2

        arg = opts.angle
        
        CmdUI.send_cmd(1, 1, command_num, arg)




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
        

        CmdUI.send_cmd(1, 1, command_num, arg)




    #filling arming command with angle argument
    filling = Cmd2ArgumentParser(description='arming of filling and setting angle of servo')
    filling.add_argument('--arming', type=str, help='arming of oxidiser filling', choices=['a','d'])
    filling.add_argument('--angle', type=int, help='angle of fill valve servo 0-180 degrees', choices=range(0,180))
    
    @with_argparser(filling) 
    def do_fill(self,opts):
        if opts.arming.arm:
            command_num = 1
        if opts.arming.disarm:
            command_num = 2

        arg = opts.angle

        CmdUI.send_cmd(1, 1, command_num, arg)




    #launch command
    def do_launch(self):
        
        command_num = 1

        arg = 0

        CmdUI.send_cmd(1,1,command_num,arg)




    #abort command
    def do_abort(self):
        
        command_num = 1

        arg = 0

        CmdUI.send_cmd(1,1,command_num,arg)




    #ignition command
    def do_ignite(self):
        
        command_num = 1

        arg = 0

        CmdUI.send_cmd(1,1,command_num,arg)




    #retract QD command
    def do_retract(self):

        command_num = 1

        arg = 0

        CmdUI.send_cmd(1,1,command_num,arg)