import serial
import time

ser = serial.Serial(port=None, baudrate=115200,timeout=0.1,write_timeout=0.1)  # open serial port
ser.port = "/dev/tty.usbmodem101"


ser.stopbits = serial.STOPBITS_ONE
ser.parity = serial.PARITY_NONE
ser.bytesize = serial.EIGHTBITS

ser.rts = False
ser.dtr = False

ser.open()


ser.rts = True
ser.dtr = True

#force esp32 reset

ser.rts = False
time.sleep(0.005) #minimal EN delay from idf_monitor.py->constants.py
ser.rts = True

prevTime = 0


b = 0x65

# time.sleep(3) #delaying allows serial.begin to be called and bug magically dissapears...

while (True):
    while (ser.in_waiting): #read out boot messages
        incomming = ser.read(1)
        try:
            print(incomming.decode('UTF-8'),end="")
        except:
            print(str(incomming),end="")
 
    
    if (time.time_ns() - prevTime > 50e6):
        # print('writing')
        prevTime = time.time_ns()
        try:
            ser.write([b])
        except serial.SerialTimeoutException:
            pass
            print('timeout')

    
