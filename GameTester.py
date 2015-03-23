# Copyright (C) 2015 and beyond by Jeremiah Morris
# and contributing developers.
#
# This file is part of Metaserver.
#
# Metaserver is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# Metaserver is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Metaserver. If not, see <http://www.gnu.org/licenses/>.

import struct

from twisted.internet.protocol import ClientFactory, DatagramProtocol
from twisted.internet import reactor, task
from MetaProtocol import MetaProtocol
from MetaPackets import unpack_strings
import random
import crcmod

### packets

class HelloPacket:
  code = 700
  
  def __init__(self, data):
    (self.version, stringlen) = unpack_strings(data)

class JoinerInfoPacket:
  code = 701
  _fmt_start = struct.Struct('>H')
  _fmt_end = struct.Struct('>HH')
  
  def __init__(self, stream_id, player_name, version, color, team):
    self.data = self._fmt_start.pack(stream_id)
    self.data += player_name + '\x00'
    self.data += version + '\x00'
    self.data += self._fmt_end.pack(color, team)

class JoinPlayerPacket:
  code = 702
  
  def __init__(self, data):
    pass

class CapabilitiesPacket:
  code = 703
  _fmt_value = struct.Struct('>L')
  
  def __init__(self, data):
    self.data = data
    self.capabilities = {}
    offset = 0
    max = len(data) - 4
    while offset < max:
      pos = data.find('\x00', offset, max)
      if pos < 0:
        offset = max
      else:
        key = data[offset:pos]
        val, = self._fmt_value.unpack_from(data, pos + 1)
        self.capabilities[key] = val
        offset = pos + 5

class AcceptJoinPacket:
  code = 704
  _fmt_start = struct.Struct('>BLHLHHHB')
  _fmt_end = struct.Struct('>HHH10s')
  
  def __init__(self, player_name):
    # accepted, dspAddress.host, dspAddress.port, ddpAddress.host, ddpAddress.port,
    # identifier, stream_id, net_dead, player_name, desired_color, team, color, serial_number
    self.data = self._fmt_start.pack(1, 0, 0, 0, 0, 0, 0, 0)
    self.data += player_name + '\x00'
    self.data += self._fmt_end.pack(0, 0, 0, '')

class TopologyPacket:
  code = 705
  
  def __init__(self, data):
    pass

class MapPacket:
  code = 706
  
  def __init__(self, data):
    pass

class PhysicsPacket:
  code = 707
  
  def __init__(self, data):
    pass

class LuaPacket:
  code = 708
  
  def __init__(self, data):
    pass

class NetworkChatPacket:
  code = 709
  _fmt = struct.Struct('>HHH')
  
  def __init__(self, data):
    self.sender_id, self.target, self.target_id, = self._fmt.unpack_from(data)
    self.message, stringlen = unpack_strings(data, 1, self._fmt.size)

class EndGameDataPacket:
  code = 711
  
  def __init__(self, data):
    pass

class ChangeColorsPacket:
  code = 712

class ServerWarningPacket:
  code = 713

class ClientInfoPacket:
  code = 714
  _fmt = struct.Struct('>HHHH')
  
  def __init__(self, data):
    self.stream_id, self.action, self.color, self.team, = self._fmt.unpack_from(data)
    self.player_name, stringlen = unpack_strings(data, 1, self._fmt.size)

class ZippedMapPacket:
  code = 715
  
  def __init__(self, data):
    pass

class ZippedPhysicsPacket:
  code = 716
  
  def __init__(self, data):
    pass

class ZippedLuaPacket:
  code = 717
  
  def __init__(self, data):
    pass

class NetworkStatsPacket:
  code = 718
  
  def __init__(self, data):
    pass

class GameSessionPacket:
  code = 719
  
  def __init__(self, data):
    pass

### connector
class JoinerConnector(MetaProtocol):

  _join_recv_packets = [ 
      HelloPacket,
      CapabilitiesPacket,
      ServerWarningPacket,
      ClientInfoPacket,
      NetworkChatPacket,
      JoinPlayerPacket,
      GameSessionPacket,
      TopologyPacket,
      MapPacket,
      PhysicsPacket,
      LuaPacket,
      ZippedMapPacket,
      ZippedPhysicsPacket,
      ZippedLuaPacket,
      EndGameDataPacket,
      NetworkStatsPacket
    ]

  def __init__(self, tester):
    MetaProtocol.__init__(self)
    self.tester = tester
    self.player_name = 'joinerbot'
    self.color = 0
    self.team = 0
    self.connected = False
    self.succeeded = False
  
  def connectionMade(self):
    MetaProtocol.connectionMade(self)
    self.tester.joinConnectSucceeded(self)
    self.connected = True
  
  def connectionLost(self, reason):
    if self.connected and not self.succeeded:
      self.tester.joinDisconnected(self, reason)
    pass

  def messageAllowed(self, code):
    for p in self._join_recv_packets:
      if p.code == code:
        return True
    return False

  def packMessage(self, code, data):
    for p in self._join_recv_packets:
      if p.code == code:
        return p(data)
    return None
    
  def packetReceived(self, packet):
    if isinstance(packet, HelloPacket):
      self.tester.joinGotHello(self)
      self.sendPacket(JoinerInfoPacket(0, self.player_name, packet.version, self.color, self.team))
      return True
    if isinstance(packet, CapabilitiesPacket):
      # self.sendPacket(CapabilitiesPacket(packet.data))
      # return True
      self.tester.joinGotCapabilities(self, packet)
      return False
    if isinstance(packet, ClientInfoPacket):
      return True
    if isinstance(packet, JoinPlayerPacket):
      self.sendPacket(AcceptJoinPacket(self.player_name))
      return True
    if isinstance(packet, GameSessionPacket):
      return True
    if isinstance(packet, TopologyPacket):
      return True
    if isinstance(packet, NetworkChatPacket):
      return True
    if isinstance(packet, MapPacket):
      return True
    if isinstance(packet, PhysicsPacket):
      return True
    if isinstance(packet, LuaPacket):
      return True
    if isinstance(packet, ZippedMapPacket):
      return True
    if isinstance(packet, ZippedPhysicsPacket):
      return True
    if isinstance(packet, ZippedLuaPacket):
      return True
    if isinstance(packet, EndGameDataPacket):
      return True
    if isinstance(packet, NetworkStatsPacket):
      return True
    return False

class JoinerConnectorFactory(ClientFactory):
  def __init__(self, tester):
    self.tester = tester
      
  def startedConnecting(self, connector):
    pass

  def buildProtocol(self, addr):
    return JoinerConnector(self.tester)

  def clientConnectionLost(self, connector, reason):
    pass

  def clientConnectionFailed(self, connector, reason):
    self.tester.joinConnectFailed(reason)

## UDP connector
class GameConnector(DatagramProtocol):

  def __init__(self, tester, host, port):
    self.tester = tester
    self.gather_host = host
    self.gather_port = port

  def startProtocol(self):
#     self.transport.connect(self.gather_host, self.gather_port)
    self.ping_id = int(random.uniform(1, 65535))
    self.ping_failed = 0
    self.timeout = reactor.callLater(0.35, self.pingTimeout)
    self.sendPing(self.ping_id)
  
  def pingTimeout(self):
    if self.ping_failed < 2:
      self.ping_failed += 1
      self.sendPing(self.ping_id)
      reactor.callLater(0.35, self.pingTimeout)
    else:
      self.tester.gameConnectFailed(self)
      self.transport.stopListening()

  def connectionRefused(self):
    self.tester.gameConnectFailed(self)
  
  def datagramReceived(self, data, (host, port)):
    _fmt = struct.Struct('>2sH')
    _magic, _crc, = _fmt.unpack_from(data)
    _dataOffset = _fmt.size
    
    crc16 = crcmod.predefined.Crc('crc-ccitt-false')
    crc16.update(_magic)
    crc16.update('\x00\x00')
    crc16.update(data[_dataOffset:])
    
    if crc16.crcValue != _crc:
      self.tester.gamePacketFailed(self, "CRC failed")
      return
    
    if _magic != 'PR':
      self.tester.gamePacketFailed(self, "bad packet type")
      return
    
    _fmt2 = struct.Struct('>H')
    _ping_id, = _fmt2.unpack_from(data, _dataOffset)
    
    if _ping_id != self.ping_id:
      self.tester.gamePacketFailed(self, "wrong ping ID")
      return
    
    self.tester.gamePingSucceeded(self)
    if self.timeout:
      self.timeout.cancel()
      self.timeout = None
    self.transport.stopListening()
 
  def sendPing(self, ping_id):
    _magic = 'PQ'
    _payload = struct.Struct('>H').pack(ping_id)
    
    crc16 = crcmod.predefined.Crc('crc-ccitt-false')
    crc16.update(_magic)
    crc16.update('\x00\x00')
    crc16.update(_payload)
    _data = _magic + crc16.digest() + _payload
    
    self.transport.write(_data, (self.gather_host, self.gather_port))

class GameTester:

  def __init__(self, host, port):
    self.test_host = host
    self.test_port = port
    self.message_callback = None
    self.finished_callback = None
    self.cancelled = False
    self.warned = False
    self.join_running = False
    self.game_running = False
  
  def setMessageCallback(self, cb=None):
    self.message_callback = cb
  
  def setFinishedCallback(self, cb=None):
    self.finished_callback = cb
  
  def run(self):
    self.join_running = True
    reactor.connectTCP(self.test_host, self.test_port, JoinerConnectorFactory(self), 3)

  def cancel(self):
    if not self.cancelled:
      self.cancelled = True
      self.finished_callback = None
      self.message_callback = None
  
  def _finished(self, success):
    if self.finished_callback is not None:
      self.finished_callback(self, success, self.warned)
      self.finished_callback = None
    self.message_callback = None

  def _sendMessage(self, msg):
    if self.message_callback is not None:
      self.message_callback(self, msg)
  
  def joinConnectFailed(self, reason):
    if self.join_running:
      self._sendMessage("TCP connection to port %d failed." % (self.test_port))
      self._finished(False)
  
  def joinDisconnected(self, connector, reason):
    if self.join_running:
      self._sendMessage("Bad response on TCP port %d." % (self.test_port))
      self._sendMessage(reason)
      self._finished(False)
  
  def joinConnectSucceeded(self, connector):
#     if self.join_running:
#       self._sendMessage("TCP connection to port %d succeeded." % (self.test_port))
    pass
  
  def joinGotHello(self, connector):
#     if self.join_running:
#       self._sendMessage("Hello packet received.")
    pass
  
  def joinGotCapabilities(self, connector, packet):
    if self.join_running:
#       self._sendMessage("Capabilities packet received.")
      self.join_running = False
      caps = packet.capabilities
      self.testCapabilities(caps)
      if "Gameworld" in caps and caps["Gameworld"] >= 3 and "Star" in caps:
        self.testUDP()
      else:
        self._finished(True)
    
  def testCapabilities(self, caps):
    if "Ring" in caps and "Star" not in caps:
      self._sendMessage("The ring protocol is deprecated. Please use star.")
      self.warned = True
    elif ("Gameworld" not in caps or caps["Gameworld"] < 2 or
          "Lua" not in caps or caps["Lua"] < 2 or
          "Star" not in caps or caps["Star"] < 6 or
          "ZippedData" not in caps or caps["ZippedData"] < 1):
      self._sendMessage("You are not network compatible with the latest version.")
      self.warned = True
  
  def testUDP(self):
    self.game_running = True
    gc = GameConnector(self, self.test_host, self.test_port)
    reactor.listenUDP(0, gc)
    
  def gameConnectSucceeded(self, connector):
#     if self.game_running:
#       self._sendMessage("UDP connection to port %d succeeded." % (self.test_port))
    pass
  
  def gameConnectFailed(self, connector):
    if self.game_running:
      self._sendMessage("UDP connection to port %d failed." % (self.test_port))
      self.game_running = False
      self._finished(False)
    
  def gamePacketFailed(self, connector, reason):
    if self.game_running:
      self._sendMessage("Bad response on UDP port %d." % (self.test_port))
      self.game_running = False
      connector.transport.stopListening()
      self._finished(False)
  
  def gamePingSucceeded(self, connector):
    if self.game_running:
#       self._sendMessage("UDP ping to port %d succeeded." % (self.test_port))
      self.game_running = False
      self._finished(True)
