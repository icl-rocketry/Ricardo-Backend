# from .packets import *
from pylibrnp.rnppacket import DeserializationError, RnpHeader
import serial
import time
from cobs import cobs
import signal
import sys
import socket
import multiprocessing as mp
from queue import Full, Empty


class SerialManager():
	SimpleSend:int = 0
	WaitForIncomming:int = 1

	def __init__(self, device, baud=115200, waittime = .3,sendQ = None,receiveQ_dict = None,verbose=False,UDPMonitor=False,UDPIp='127.0.0.1',UDPPort=7000):
		signal.signal(signal.SIGINT,self.exitHandler)
		signal.signal(signal.SIGTERM,self.exitHandler)
		self.device = device
		self.baud = baud
		self.waittime = waittime
		
		self.sendMode = SerialManager.SimpleSend
		self.prevSendTime = 0

		 
		self.sendDelta = 1e4

		self.sentWaitTimeout:int=1000e6
		self.received_packet:bool=False

		self.verbose = verbose
		

		self.packetRecordTimeout = 2*60 #default 2 minute timeout
		self.messageQueueSize = 5000
		self.receiveBuffer = []

		self.packetRecord = {} # dict -> {uid:identifier:dict}
		self.counter = 0

		self.receivedQueueTimeout = 10*60 #default 10 minute timeout

		# self.redishost = redishost
		# self.redisport= redisport

		if sendQ is None or receiveQ_dict is None:
			raise Exception('[Serial-Manager]: Error, no sendqueue or receivequeue passed, exiting')

		self.sendQ:mp.Queue = sendQ
		self.receiveQ_dict:dict = receiveQ_dict #{"prefix1":mp.Queue,"prefix2":mp.Queue}...

		#connect to redis 
		# self.rd = redis.Redis(host = self.redishost,port = self.redisport)
		#clear SendQueue
		# self.rd.delete("SendQueue")

		self.UDPMonitor = UDPMonitor
		#setup udp monitor
		if (UDPMonitor):
			self.UDPIp = UDPIp
			self.UDPPort = UDPPort
			self.sock = None

		
	def run(self):
		with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as self.sock:
			self.__connect__() #connect to ricardo 
			
			while True:
				self.__checkSendQueue__()
				self.__readPacket__()
				self.__cleanupPacketRecord__()
		
	def exitHandler(self,sig,frame):
		print("Serial Manager Exited")
		self.ser.close() #close serial port
		sys.exit(0)

		
	def __connect__(self):
		boot_messages = ''
		self.ser = serial.Serial(port=self.device, baudrate=self.baud, timeout = self.waittime)  # open serial port

		self.ser.stopbits = serial.STOPBITS_ONE
		self.ser.parity = serial.PARITY_NONE
		self.ser.bytesize = serial.EIGHTBITS

		#print('call reset on esp32')
		self.ser.setDTR(False)
		time.sleep(1)
		self.ser.flushInput()
		self.ser.setDTR(True)
		#print('esp32 reset')
		self.ser.flushInput()

		#get boot messages after reboot
		while (self.ser.in_waiting):
			data = self.ser.read(1)
			try:
				boot_messages += data.decode("utf-8")
			except:
				boot_messages += str(data)
		# if self.verbose:
		print(boot_messages)

	def __readPacket__(self):
		#cobs decode
		while self.ser.in_waiting > 0:
			incomming = self.ser.read(1)
		
			# try:
			# 	print(incomming.decode('UTF-8'),end="")
			# except:
			# 	print(str(incomming),end="")
			if self.verbose:
				# print(str(incomming))
				try:
					print(incomming.decode('UTF-8'),end="")
				except:
					print(str(incomming),end="")

			if (incomming == (0x00).to_bytes(1,'little')):
				if (len(self.receiveBuffer) == 0):
					#empty frame receved, discard this
					return
				try:
					decodedData = cobs.decode(bytearray(self.receiveBuffer))
					self.__processReceivedPacket__(decodedData)
					self.__sendToUDP__(decodedData) 
					# print(decodedData)
				except cobs.DecodeError as e:
					print("Decoded Error, the following data could not be decoded...")
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
			print("Deserialization Error")
			print(data)
			return
		#check header len
		
		if (len(data) != (RnpHeader.size + header.packet_len)):
			print("Length Mismatch expected:" + str((RnpHeader.size + header.packet_len)) + " Received: " + str(len(data)))
			print(data.hex())
			return

		uid = header.uid #get unique id
	
		if uid in self.packetRecord:
			#get client id from packetrecord and remove corresponding entry
			identifier = self.packetRecord.pop(uid)[0]
			#retreive the appropriate queue
			try:
				queue:mp.Queue = self.receiveQ_dict[identifier['prefix']]
			except KeyError:
				print('[Serial-Manager]: Invalid key: ' + identifier['prefix'] + 'dumping packet!')
				return

			try:
				sendData = {'identifier':identifier,'type':'response','data':data}
				queue.put_nowait(sendData)
			except Full:
				print('[Serial-Manager]: receive queue full, dumping packet!')
				return


		else:
			#handle packets addressed to the local packet handler on the backend
			if (uid == 0) and (header.destination_service == 0):
				self.__localPacketHandler__(data)
				
				return

			#unkown packet received -> dump packet ; might be worth spewing these into a file
			print("[ERROR-BACKEND] unkown packet recieved")
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
		#check if there are items present in send queue
		# if (time.time_ns() - self.prevSendTime) > self.sendDelta :
		if (self.sendMode == SerialManager.WaitForIncomming):
			if (self.received_packet):
				self.__processSendQueue__()
				self.received_packet = False
			elif (time.time_ns() - self.prevSendTime > self.sentWaitTimeout):
				# print("receive timeout, sending new packet")
				self.__processSendQueue__()
		elif (self.sendMode == SerialManager.SimpleSend):
			if (time.time_ns()-self.prevSendTime > self.sendDelta):
				self.__processSendQueue__()
		
			
	
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

	def __localPacketHandler__(self,data:bytes):
		#decode header
		header = RnpHeader.from_bytes(data)
		if (header.packet_type == 100): #message packet
			packet_body = data[RnpHeader.size:]
			try:
				message:str = packet_body.decode('UTF-8') 
			except:
				message:str = str(packet_body)
			if self.verbose:
				print("Message: " + message)
			json_message = {"header" : vars(header),
							"message": message}
			#broadcast message to all receive queues
			for queue in self.receiveQ_dict.values():
				try:
					json_message['type'] = "logmessage"
					queue.put_nowait(json_message)
				except Full:
					print('[Serial-Manager]: receive Queue full, skipping message')

			return
		
