from apps.pylibrnp.defaultpackets import SimpleCommandPacket
from pylibrnp import rnppacket
from pylibrnp import defaultpackets


c = SimpleCommandPacket()

print(vars(c))

def packet_init(self):

    # self.command = 0
    # self.arg = 2

    # print(super())
    rnppacket.RnpPacket.__init__(self,['command','arg'],
                        SimpleCommandPacket.struct_str,
                        SimpleCommandPacket.size,
                        SimpleCommandPacket.packet_type)

c2 = type('packet',(rnppacket.RnpPacket,),{'__init__':packet_init})
c_instance = c2()
setattr(c_instance,'command',0)
setattr(c_instance,'arg',2)
# c2.__init__ = packet_init

print(vars(c_instance))  
print(c_instance.packetvars)

print(c_instance.getData())
# print(c2().arg)

class test():
    def __exit__(self,*args):
        print('destructor called')


container = {"t1",test()}
print(container)
container = {}
