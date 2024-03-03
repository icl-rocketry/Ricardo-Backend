# from .packets import *
from pylibrnp.rnppacket import DeserializationError, RnpHeader
import serial
from serial import SerialException
import time
from cobs import cobs
import signal
import sys
import socket
import multiprocessing as mp
from queue import Full, Empty


class SerialManager():

	def __init__(self, device, baud=115200, autoreconnect=True, waittime = .3,sendQ = None,receiveQ = None,verbose=False,UDPMonitor=False,UDPIp='127.0.0.1',UDPPort=7000):
		signal.signal(signal.SIGINT,self.exitHandler)
		signal.signal(signal.SIGTERM,self.exitHandler)
		self.device = device
		self.baud = baud
		self.autoreconnect = autoreconnect
		self.waittime = waittime
		
		self.prevSendTime = 0

		 
		self.sendDelta = 1e4

		self.verbose = verbose
		

		self.packetRecordTimeout = 2*60 #default 2 minute timeout
		self.messageQueueSize = 5000
		self.receiveBuffer = []

		self.packetRecord = {} # dict -> {uid:identifier:dict}
		self.counter = 0

		self.receivedQueueTimeout = 10*60 #default 10 minute timeout

		if sendQ is None or receiveQ is None:
			raise Exception('[Serial-Manager] - Error, no sendqueue or receivequeue passed, exiting')

		self.sendQ:mp.Queue = sendQ
		# self.receiveQ_dict:dict = receiveQ_dict #{"prefix1":mp.Queue,"prefix2":mp.Queue}...
		self.receiveQ:dict = receiveQ

		self.UDPMonitor = UDPMonitor
		self.sock = None
		#setup udp monitor
		if (UDPMonitor):
			self.UDPIp = UDPIp
			self.UDPPort = UDPPort
			

		self.localPacketHandlerCallbacks:dict = {}
		#refister default message packet callback on serial manager
		#callback must have the folloing type 
		#def cb1(data:bytes)
	
		self.registerLocalPacketHandlerCallback(100,self.__decodeMessagePacket__)

		
	def run(self):
		with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as self.sock:
			self.__auto_connect__()
			
			while True:
				try:
					self.__checkSendQueue__()
					self.__readPacket__()
					self.__cleanupPacketRecord__()
					time.sleep(0.001)
				except (OSError, serial.SerialException):
					self.__disconnect__()
					self.__auto_connect__()

					
		
	def exitHandler(self,sig,frame):
		self.__sm_log__("Serial Manager Exited")
		self.__disconnect__()
		sys.exit(0)

	def __auto_connect__(self):
		while True:
			try:
				self.__connect__()
				self.__sm_log__("Device " + self.device + " Connected")
				break
			except (OSError, serial.SerialException):
				if self.autoreconnect:
					self.__sm_log__('Device ' + self.device + ' Disconnected, retrying...')
					time.sleep(1)
					continue
				else:
					self.__sm_log__('Device ' + self.device + ' Disconnected, killing serial manager. Bye bye!')
					self.exitHandler(None,None)
	
	def __disconnect__(self):
		try:
			self.ser.close()
		except AttributeError:
			pass

	def __connect__(self):
		boot_messages = ''
		self.ser = serial.Serial(port=None, baudrate=self.baud, timeout = self.waittime)  # open serial port
		self.ser.port = self.device

		self.ser.stopbits = serial.STOPBITS_ONE
		self.ser.parity = serial.PARITY_NONE
		self.ser.bytesize = serial.EIGHTBITS

		self.ser.rts = False
		self.ser.dtr = False
		
		self.ser.open()

		self.ser.rts = True
		self.ser.dtr = True
		
		#force esp32 reset

		self.ser.rts = False
		time.sleep(0.005) #minimal EN delay from idf_monitor.py->constants.py
		self.ser.rts = True

		# self.ser.flushInput()
		# self.ser.setDTR(True)
		#self.__sm_log__('esp32 reset')
		# self.ser.flushInput()

		#get boot messages after reboot
		# while (self.ser.in_waiting):
		# 	data = self.ser.read(1)
		# 	try:
		# 		boot_messages += data.decode("utf-8")
		# 	except:
		# 		boot_messages += str(data)
		# # if self.verbose:
		# self.__sm_log__(boot_messages)

	def __readPacket__(self):
		#cobs decode
		while self.ser.in_waiting > 0:
			incomming = self.ser.read(1)
		
			# try:
			# 	print(incomming.decode('UTF-8'),end="")
			# except:
			# 	print(str(incomming),end="")
			if self.verbose:
				# self.__sm_log__(str(incomming))
				try:
					print(incomming.decode('UTF-8'),end="")
				except:
					print(str(incomming),end="")

			if (incomming == (0x00).to_bytes(1,'little')):
				if (len(self.receiveBuffer) == 0):
					#empty frame receved, discard this
					# return
					break
				try:
					decodedData = cobs.decode(bytearray(self.receiveBuffer))
					self.__processReceivedPacket__(decodedData)
					self.__sendToUDP__(decodedData) 
					# self.__sm_log__(decodedData)
				except cobs.DecodeError as e:
					self.__sm_log__("Decoded Error, the following data could not be decoded...")
					print(e)
					print(self.receiveBuffer)
					
				#empty receive buffer
				self.receiveBuffer = []
			else:
				#place new byte at end of buffer
				self.receiveBuffer += incomming
 
	def __processReceivedPacket__(self,data:bytes):
		self.received_packet = True

		try:
			header = RnpHeader.from_bytes(data)#decode header
		except DeserializationError:
			self.__sm_log__("Deserialization Error")
			self.__sm_log__(str(data))
			return
		#check header len
		
		if (len(data) != (RnpHeader.size + header.packet_len)):
			self.__sm_log__("Length Mismatch expected:" + str((RnpHeader.size + header.packet_len)) + " Received: " + str(len(data)))
			self.__sm_log__(data.hex())
			return

		uid = header.uid #get unique id
	
		if uid in self.packetRecord:
			#get client id from packetrecord and remove corresponding entry
			identifier = self.packetRecord.pop(uid)[0]

			try:
				sendData = {'identifier':identifier,'type':'response','data':data}
				self.receiveQ.put_nowait(sendData)
			except Full:
				self.__sm_log__('receive queue full, dumping packet!')
				return


		else:
			#handle packets addressed to the local packet handler on the backend
			if (uid == 0) and (header.destination_service == 0):
				self.localPacketHandlerCallbacks.get(header.packet_type,lambda: None)(data)
				
				return

			#unkown packet received -> dump packet ; might be worth spewing these into a file
			self.__sm_log__("unkown packet recieved")
			print(header)
			return

			
	def __sendPacket__(self,data:bytes,identifier:dict):
		header = RnpHeader.from_bytes(data)#decode header
		uid = self.__generateUID__() #get uuid
		header.uid = uid #get uuid
		serialized_header = header.serialize() #re-serialize header
		modifieddata = bytearray(data)
		modifieddata[:len(serialized_header)] = serialized_header
		self.packetRecord[uid] = [identifier,time.time()] #update packetrecord dictionary
		#self.sendBuffer.append(data)#add packet to send buffer
		self.__sendToUDP__(modifieddata)  #send data to udp monitor
		# cobs encode
		encoded = bytearray(cobs.encode(modifieddata))
		encoded += (0x00).to_bytes(1,'little') #add end packet marker
		self.ser.write(encoded)#write packet to serial port and hope its free lol
		

	def __checkSendQueue__(self):
		if (time.time_ns()-self.prevSendTime > self.sendDelta):
				self.__processSendQueue__()
				self.prevSendTime = time.time_ns()

	def __sm_log__(self,msg):
		#serial maanger logger, will replace with something better than self.__sm_log__ in the future - famous last words
		print('[Serial Manager] - ' + str(msg))	
			
	
	def __processSendQueue__(self):
		try:
			#item is a json object with structure 
			#{data:bytes as hex string,
			# identifier:"{}"}
			item = self.sendQ.get_nowait()
			self.__sendPacket__(bytes.fromhex(item['data']),item['identifier'])
			self.prevSendTime = time.time_ns()
		except Empty:
			return
	
		

	def __generateUID__(self):
		#UID is a unsigend 16bit integer. UID 0 is reserved for forwarding to local so we want 
		#strictly increasing integers in the range [1 65535]
		self.counter = (self.counter%65535) + 1
		return self.counter 
			
	def __cleanupPacketRecord__(self):
		expiry_time = time.time() - self.packetRecordTimeout
		
		#use list to force python to copy items
		for key,value in list(self.packetRecord.items()):
			if value[1] < expiry_time:
				self.packetRecord.pop(key) #remove entry

	def __sendToUDP__(self,data:bytearray):
		if (self.UDPMonitor):
			self.sock.sendto(data,(self.UDPIp,self.UDPPort))

		
	def registerLocalPacketHandlerCallback(self,packet_type:int,callback):
		#will override any existing callbacks
		self.localPacketHandlerCallbacks[packet_type] = callback

	def __decodeMessagePacket__(self,data:bytes):
		header = RnpHeader.from_bytes(data)
		packet_body = data[RnpHeader.size:]
		try:
			message:str = packet_body.decode('UTF-8') 
		except:
			message:str = str(packet_body)
		if self.verbose:
			self.__sm_log__("Message: " + message)
		json_message = {"header" : vars(header),
						"message": message}
	
		try:
			json_message['type'] = "logmessage"
			self.receiveQ.put_nowait(json_message)
		except Full:
			self.__sm_log__('receive Queue full, skipping message')



		
