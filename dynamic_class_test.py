from apps.pylibrnp.defaultpackets import SimpleCommandPacket
from pylibrnp import rnppacket
from pylibrnp import defaultpackets


c = SimpleCommandPacket()

print(vars(c))

def packet_init(self,**kwargs):

    self.command = 0
    self.arg = 2

    super(rnppacket.RnpPacket, self).__init__(['command','arg'],
                        SimpleCommandPacket.struct_str,
                        SimpleCommandPacket.size,
                        SimpleCommandPacket.packet_type)

c2 = type('packet',(rnppacket.RnpPacket,),{})
c2.__init__ = packet_init
print(vars(c2()))  