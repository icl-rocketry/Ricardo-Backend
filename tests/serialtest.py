import serial

ser = serial.Serial(port="/dev/tty.usbmodem101", baudrate=115200)

while(True):
    print(ser.read(1))
    