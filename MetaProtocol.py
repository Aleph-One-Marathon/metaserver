# Copyright (C) 2014 and beyond by Jeremiah Morris
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

from twisted.internet.protocol import Protocol
from twisted.protocols.policies import TimeoutMixin
from twisted.python import log
from twisted.internet.error import ConnectionDone
from MetaPackets import *
import pprint

class MetaProtocol(Protocol, TimeoutMixin):

  TIMEOUT = 10
  MAX_LENGTH = 10240
  SIGNATURE = 0xDEAD
  _fmt = struct.Struct('>HHL')
  _all_recv_packets = [ LoginPacket, PasswordResponsePacket, LocalizationPacket, LogoutPacket, RoomLoginPacket, PlayerDataPacket, PlayerModePacket, CreateGamePacket, StartGamePacket, RemoveGamePacket, IncomingChatPacket, IncomingPrivateMessagePacket, IncomingKeepAlivePacket ]
  
  def __init__(self):
#     Protocol.__init__(self)
    self._unprocessed = b''
    self._awaitingPing = False
      
  def connectionMade(self):
    conn = self.transport.getPeer()
    log.msg("new connection on %s:%d" % (conn.host, conn.port))
    self.setTimeout(self.TIMEOUT)
  
  def connectionLost(self, reason):
    if reason.type == ConnectionDone:
      log.msg("closed connection")
    else:
      log.msg("lost connection: %s" % str(reason))
    self.setTimeout(None)
  
  def resetTimeout(self):
    self._awaitingPing = False
    TimeoutMixin.resetTimeout(self)
  
  def timeoutConnection(self):
    if self._awaitingPing:
      # keepalive packet timed out
      self.transport.loseConnection()
    else:
      self._awaitingPing = True
      self.sendPacket(OutgoingKeepAlivePacket())
      self.setTimeout(self.TIMEOUT)
  
  def messageAllowed(self, code):
    for p in self._all_recv_packets:
      if p.code == code:
        return True
    return False
  
  def packetReceived(self, packet):
    return False
  
  def packMessage(self, code, data):
    for p in self._all_recv_packets:
      if p.code == code:
        return p(data)
    return None
  
  def sendPacket(self, packet):
    extradata = packet.data
    if extradata == None:
      extradata = b''
    if not isinstance(packet, OutgoingKeepAlivePacket):
      log.msg("sending %s (%d bytes)" % (packet.__class__.__name__.rsplit('.', 1).pop(), len(extradata)))
    data = self._fmt.pack(self.SIGNATURE, packet.code, self._fmt.size + len(extradata)) + extradata
    self.transport.write(data)
  
  def sendMessage(self, which):
    self.sendPacket(MessagePacket(which))
    
  def dataReceived(self, data):
    self.resetTimeout()
    alldata = self._unprocessed + data
    currentOffset = 0
    
    while len(alldata) >= (currentOffset + self._fmt.size):
      bodyStart = currentOffset + self._fmt.size
      signature, code, datalen = self._fmt.unpack_from(alldata, currentOffset)
      if signature != self.SIGNATURE or datalen > self.MAX_LENGTH or datalen < self._fmt.size or not self.messageAllowed(code):
        self.transport.loseConnection()
        return
      bodyEnd = currentOffset + datalen
      if len(alldata) < bodyEnd:
        break
      
      packet = self.packMessage(code, alldata[bodyStart:bodyEnd])
      if isinstance(packet, IncomingKeepAlivePacket):
        pass  # we already reset the timeout, just eat the response
      elif packet is None:  # could not unpack
        self.transport.loseConnection()
        return
      else:
        debugdata = ''
        if not getattr(packet, 'private', False):
           debugdata = "\n" + pprint.pformat(vars(packet))
        log.msg("received %s (%d bytes)%s" % (packet.__class__.__name__.rsplit('.', 1).pop(), bodyEnd - bodyStart, debugdata))
        if not self.packetReceived(packet):
          self.transport.loseConnection()
          return
      
      currentOffset = bodyEnd
    
    self._unprocessed = alldata[currentOffset:]
