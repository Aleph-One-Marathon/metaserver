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

from twisted.internet.protocol import Factory
from twisted.python import log
from MetaProtocol import MetaProtocol
from MetaPackets import *
import pprint
import time

class Roomd(MetaProtocol):
  NEED_LOGIN = 0
  NEED_PLAYER_DATA = 1
  LOGGED_IN = 2
  
  VERB_ADD = 0
  VERB_DELETE = 1
  VERB_CHANGE = 2
  
  def __init__(self, factory):
    MetaProtocol.__init__(self)
    self.factory = factory
    self.userd = factory.userd_factory
    self.globals = factory.userd_factory.globals
    self.state = self.NEED_LOGIN
    self.deaf = True
    self.user_id = None
    self.user_info = None
    self.game_info = None
    self.dbpool = self.userd.dbpool
  
  def packetReceived(self, packet):  
    if isinstance(packet, RoomLoginPacket):
      return self.handleRoomLoginPacket(packet)
    if isinstance(packet, PlayerDataPacket):
      return self.handlePlayerDataPacket(packet)
    if isinstance(packet, PlayerModePacket):
      return self.handlePlayerModePacket(packet)
    if isinstance(packet, CreateGamePacket):
      return self.handleCreateGamePacket(packet)
    if isinstance(packet, StartGamePacket):
      return self.handleStartGamePacket(packet)
    if isinstance(packet, RemoveGamePacket):
      return self.handleRemoveGamePacket(packet)
    if isinstance(packet, IncomingChatPacket):
      return self.handleIncomingChatPacket(packet)
    if isinstance(packet, IncomingPrivateMessagePacket):
      return self.handleIncomingPrivateMessagePacket(packet)
    if isinstance(packet, LogoutPacket):
      return self.handleLogoutPacket(packet)
    return False
      
  def handleRoomLoginPacket(self, packet):
    if self.state != self.NEED_LOGIN:
      self.sendMessage(MessagePacket.USER_LOGGED_IN)
      return False
    self.user_id = self.userd.redeemToken(packet.token)
    if self.user_id is None:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    self.user_info = self.globals['users'][self.user_id]
    uname = self.user_info['username']
    if uname is None:
      uname = 'guest'
    if uname != packet.username:
      self.sendMessage(MessagePacket.BAD_USER)
      return False
    
    self.state = self.NEED_PLAYER_DATA
    self.user_info['roomd_connection'] = self
    return True
  
  def handlePlayerDataPacket(self, packet):
    if self.state != self.NEED_PLAYER_DATA:
      if self.state == self.NEED_LOGIN:
        self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      else:
        self.sendMessage(MessagePacket.USER_LOGGED_IN)
      return False
    
    # we actually ignore the data; we kept it from userd
    # just log them in
    self.logEvent('login', pprint.pformat(vars(self.user_info['player_info'])))
    self.state = self.LOGGED_IN
    self.deaf = False
    self.sendPacket(RoomLoginSuccessfulPacket(self.user_id))
    self.sendMessage(MessagePacket.LOGIN_SUCCESSFUL)
    
    # MOTD
    uname = self.user_info['username']
    if uname is None:
      self.sendPacket(RoomMessagePacket("Tired of being a guest? Sign up at: http://metaserver.lhowon.org"))
    else:
      self.sendPacket(RoomMessagePacket("Bugs? Suggestions? http://metaserver.lhowon.org/contact")
    
    # announce new player to everyone else
    self.sendPlayerList(self.user_id, 0 - self.user_id, self.VERB_ADD)
    # announce everyone to new player
    self.sendPlayerList(0, self.user_id, self.VERB_ADD)
    # announce games to new player
    self.sendGameList(0, self.user_id, self.VERB_ADD)
    
    return True
  
  def handlePlayerModePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if packet.deaf > 0:
      self.logEvent('enter game')
      self.deaf = True
    else:
      self.logEvent('leave game')
      self.deaf = False
    return True
  
  def handleCreateGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
      
    self.logEvent('create game', packet.game_data.encode('hex'))
    verb = self.VERB_CHANGE
    if self.game_info is None:
      gid = self.userd.buildGameID(self.user_id)
      self.game_info = self.globals['games'][gid]
      self.game_info['host'] = self.transport.getPeer().host
      verb = self.VERB_ADD
    
    self.game_info['port'] = packet.port
    self.game_info['game_data'] = packet.game_data
    
    # announce game to everyone
    self.sendGameList(self.game_info['game_id'], 0, verb)
    return True
  
  def handleStartGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if self.game_info is None:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    
    self.logEvent('start game', packet.game_time)
    self.game_info['start_time'] = time.time()
    if packet.game_time > 0:
      self.game_info['time_left'] = packet.game_time
    # no broadcast - Aleph One handles this through create-game data
    return True
  
  def handleRemoveGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if self.game_info is not None:
      self.logEvent('remove game')
      self.sendGameList(self.game_info['game_id'], 0, self.VERB_DELETE)
      self.userd.expireGame(self.game_info['game_id'])
    return True
  
  def handleIncomingChatPacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if packet.sender_id != self.user_id:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    
    self.logChat(packet.message)
    self.sendPacketToRoom(OutgoingChatPacket(self.user_info, packet.message))
    return True
  
  def handleIncomingPrivateMessagePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if packet.sender_id != self.user_id or packet.header_target_id != packet.target_id:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    if packet.target_id not in self.globals['users'] or self.globals['users'][packet.target_id]['roomd_connection'] is None:
      self.sendMessage(MessagePacket.NOT_IN_ROOM)
      return True
    
    out = OutgoingPrivateMessagePacket(self.user_info, packet.target_id, packet.message)
    target = self.globals['users'][packet.target_id]['roomd_connection']
    if not target.deaf:
      target.sendPacket(out)
    if packet.echo and not self.deaf:
      self.sendPacket(out)
    return True
  
  def handleLogoutPacket(self, packet):
    self.deaf = True
    # rest of cleanup will occur in connectionLost
    return False

  def connectionLost(self, reason):
    MetaProtocol.connectionLost(self, reason)
    self.user_info['roomd_connection'] = None
    if self.state == self.LOGGED_IN:
      if self.game_info is not None:
        self.logEvent('remove game')
        self.sendGameList(self.game_info['game_id'], 0, self.VERB_DELETE)
        self.userd.expireGame(self.game_info['game_id'])
      self.logEvent('logout')
      self.sendPlayerList(self.user_id, 0, self.VERB_DELETE)
    self.userd.cleanUser(self.user_id)
    self.userd.debugGlobals()

  def sendPlayerList(self, send, recip, verb):
    send_list = self.buildSendList('users', send)
    if len(send_list) > 0:
      self.sendPacketToRoom(PlayerListPacket(send_list, verb), recip)
  
  def sendGameList(self, send, recip, verb):
    send_list = self.buildSendList('games', send)
    if len(send_list) > 0:
      self.sendPacketToRoom(GameListPacket(send_list, verb), recip)
  
  def buildSendList(self, which, send):
    send_list = []
    if send > 0:
      if send in self.globals[which]:
        send_list.append(self.globals[which][send])
    else:
      for id, info in self.globals[which].iteritems():
        if info['visible'] and not id == (0 - send):
          send_list.append(info)
    return send_list
    
  def sendPacketToRoom(self, packet, recip=0):
    if packet is None:
      return False
    if recip > 0:
      if recip in self.globals['users']:
        conn = self.globals['users'][recip]['roomd_connection']
        if conn is not None and not conn.deaf:
          conn.sendPacket(packet)
    else:
      for user_id, info in self.globals['users'].iteritems():
        if not user_id == (0 - recip):
          conn = info['roomd_connection']
          if conn is not None and not conn.deaf:
            conn.sendPacket(packet)

  def logChat(self, message):
    deferred = self.dbpool.runOperation("""
      INSERT INTO chatlog
      (event_date, username, chatname, color_r, color_g, color_b, message)
      VALUES (NOW(), %s, %s, %s, %s, %s, %s)""",
      (self.user_info['username'], self.user_info['chatname'],
      self.user_info['player_info'].player_color[0],
      self.user_info['player_info'].player_color[1],
      self.user_info['player_info'].player_color[2],
      message))
    deferred.addErrback(self.reportDbError)
  
  def logEvent(self, type, data=None):
    deferred = self.dbpool.runOperation("""
      INSERT INTO eventlog
      (event_date, event_type, username, user_id, extradata)
      VALUES (NOW(), %s, %s, %s, %s)""",
      (type, self.user_info['username'], self.user_id, data))
    deferred.addErrback(self.reportDbError)
  
  def reportDbError(self, failure):
    log.msg("Database failure: %s" % str(failure))
  
  
class RoomdFactory(Factory):

  def __init__(self, userd_factory):
#     Factory.__init__(self)
    self.userd_factory = userd_factory
  
  def buildProtocol(self, addr):
    return Roomd(self)


