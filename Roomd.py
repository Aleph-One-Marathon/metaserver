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
from UserInfo import UserInfo
from GameTester import GameTester
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
    self.tester = None
    self.dbpool = self.userd.dbpool
    self.log_events = True if self.factory.options['log_events'] > 0 else False
    self.log_logindetail = True if self.factory.options['log_logindetail'] > 0 else False
    self.log_chat = True if self.factory.options['log_chat'] > 0 else False
    self.log_pm = True if self.factory.options['log_pm'] > 0 else False
    if not self.log_chat:
      self.log_pm = False
  
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
    uname = self.user_info.username
    if uname is None:
      uname = b'guest'
    if packet.username == b'':
      packet.username = b'guest'
    if uname != packet.username:
      self.sendMessage(MessagePacket.BAD_USER)
      return False
    
    self.state = self.NEED_PLAYER_DATA
    self.user_info.roomd_connection = self
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
    self.logEvent('login', pprint.pformat(vars(self.user_info.player_info)))
    self.logLogin()
    self.state = self.LOGGED_IN
    self.deaf = False
    self.user_info.in_game = False
    self.sendPacket(RoomLoginSuccessfulPacket(self.user_id))
    self.sendMessage(MessagePacket.LOGIN_SUCCESSFUL)
    
    # MOTD
    uname = self.user_info.username
    if uname is None:
      self.sendRoomMessage("Tired of being a guest? Sign up at: https://metaserver.lhowon.org")
    self.sendRoomMessage("Find players on the Discord: https://discord.gg/c7rEVgY")
    
    # announce new player to everyone else
    self.sendPlayerList(self.user_id, 0 - self.user_id, self.VERB_ADD)
    # announce everyone to new player
    self.sendPlayerList(0, self.user_id, self.VERB_ADD)
    # announce games to new player
    self.sendGameList(0, self.user_id, self.VERB_ADD)
    
    self.checkRainbow()
    return True
  
  def handlePlayerModePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    go_deaf = False
    if packet.deaf > 0:
      go_deaf = True
    if self.deaf != go_deaf:
      self.deaf = go_deaf
      self.user_info.in_game = True
      if go_deaf:
        self.logEvent('enter game', packet.session_id.hex())
      else:
        self.logEvent('leave game')
      self.sendPlayerList(self.user_id, 0, self.VERB_CHANGE)
      self.checkRainbow()
    return True
  
  def handleCreateGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
      
    self.logEvent('create game', packet.game_data.hex())
    verb = self.VERB_CHANGE
    if self.game_info is None:
      gid = self.userd.buildGameID(self.user_id)
      self.game_info = self.globals['games'][gid]
      self.game_info.host = self.transport.getPeer().host
      verb = self.VERB_ADD
    
    self.game_info.port = packet.port
    self.game_info.game_data = packet.game_data

    if packet.remote_server_id > 0:
      if any(game.remote_hub_id == packet.remote_server_id and game.game_id != self.game_info.game_id for game in self.globals['games'].values()):
        log.msg("Unexpected situation detected. Found another advertised game already using the requested remote hub id %d" % packet.remote_server_id)
        return False
      deferred = self.dbpool.runQuery("SELECT host, port FROM remotehub WHERE id = %s", (packet.remote_server_id, ))
      deferred.addCallback(lambda result: self.remoteCreateGameResult(result, packet.remote_server_id, verb))
      deferred.addErrback(self.remoteCreateGameFailure)
    else:
      # announce game to everyone
      self.sendGameList(self.game_info.game_id, 0, verb)
    
    return True
  
  def handleStartGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if self.game_info is None:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    
    if self.tester is not None:
      self.tester.cancel()
      self.tester = None
    self.logEvent('start game', packet.game_time)
    self.game_info.start_time = time.time()
    if packet.game_time > 0 and packet.game_time < 7 * 24 * 3600 * 30:
      self.game_info.time_left = packet.game_time / 30
    self.sendGameList(self.game_info.game_id, 0, self.VERB_CHANGE)
    return True
  
  def handleRemoveGamePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if self.game_info is not None:
      self.logEvent('remove game')
      self.sendGameList(self.game_info.game_id, 0, self.VERB_DELETE)
      self.userd.expireGame(self.game_info.game_id)
      self.game_info = None
    if self.tester is not None:
      self.tester.cancel()
      self.tester = None
    return True
  
  def handleIncomingChatPacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if packet.sender_id != self.user_id:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    self.userActive()
    trimmed = packet.message.strip()
    if trimmed != '':
      if not self.handleChatCommand(trimmed):
        self.logChat(trimmed)
        self.sendPacketToRoom(OutgoingChatPacket(self.user_info, trimmed))
    return True
  
  def handleIncomingPrivateMessagePacket(self, packet):
    if self.state != self.LOGGED_IN:
      self.sendMessage(MessagePacket.NOT_LOGGED_IN)
      return False
    if packet.sender_id != self.user_id or packet.header_target_id != packet.target_id:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    self.userActive()
    if not self.isUserIdVisible(packet.target_id):
      self.sendMessage(MessagePacket.NOT_IN_ROOM)
      return True
    
    trimmed = packet.message.strip()
    if trimmed != '':
      if not self.handleChatCommand(trimmed, self.globals['users'][packet.target_id]):
        out = OutgoingPrivateMessagePacket(self.user_info, packet.target_id, trimmed)
        if self.isUserIdListening(packet.target_id):
          self.globals['users'][packet.target_id].roomd_connection.sendPacket(out)
          self.logPM(self.globals['users'][packet.target_id], trimmed)
        if packet.echo and not self.deaf:
          self.sendPacket(out)
    return True
  
  def handleLogoutPacket(self, packet):
    self.deaf = True
    # rest of cleanup will occur in connectionLost
    return False

  def connectionLost(self, reason):
    MetaProtocol.connectionLost(self, reason)
    if self.user_info is not None:
      self.user_info.roomd_connection = None
    did_change = False
    if self.state == self.LOGGED_IN:
      if self.game_info is not None:
        self.logEvent('remove game')
        self.sendGameList(self.game_info.game_id, 0, self.VERB_DELETE)
        self.userd.expireGame(self.game_info.game_id)
      self.logEvent('logout')
      self.sendPlayerList(self.user_id, 0, self.VERB_DELETE)
      did_change = True
    self.userd.cleanUser(self.user_id)
    self.userd.debugGlobals()
    if did_change:
      self.checkRainbow()

  def sendRoomMessage(self, message):
    self.sendPacket(RoomMessagePacket(message.encode('mac_roman')))
  
  def broadcastRoomMessage(self, message):
    self.logBroadcast(message)
    self.sendPacketToRoom(RoomMessagePacket(message.encode('mac_roman')))

  def sendPlayerList(self, send, recip, verb):
    send_list = []
    if send > 0:
      if self.isUserIdVisible(send) or verb == self.VERB_DELETE:
        send_list.append(self.globals['users'][send])
    else:
      for info in self.visibleUsersInRoom():
        if not info.user_id == (0 - send):
          send_list.append(info)
    if len(send_list) > 0:
      self.sendPacketToRoom(PlayerListPacket(send_list, verb), recip)
  
  def sendGameList(self, send, recip, verb):
    send_list = self.buildSendList('games', send)
    if len(send_list) > 0:
      self.sendPacketToRoom(GameListPacket(send_list, verb), recip)
  
  def buildSendList(self, which, send):
    send_list = []
    if send > 0:
      if send in self.globals[which] and self.globals[which][send].visible:
        send_list.append(self.globals[which][send])
    else:
      for id, info in self.globals[which].items():
        if info.visible and not id == (0 - send):
          send_list.append(info)
    return send_list
    
  def sendPacketToRoom(self, packet, recip=0):
    if packet is None:
      return False
    if recip > 0:
      if self.isUserIdListening(recip):
        self.globals['users'][recip].roomd_connection.sendPacket(packet)
    else:
      for info in self.listeningUsersInRoom():
        if not info.user_id == (0 - recip):
          info.roomd_connection.sendPacket(packet)
            
  def remoteCreateGameResult(self, rs, server_id, verb):
    if self.state != self.LOGGED_IN:
      log.msg("Remote hub create game in wrong context")
      self.transport.loseConnection()
      return
  
    if len(rs) != 1:
      log.msg("Found %d remote servers in database for id %d. Was expecting 1." % (len(rs), server_id))
      self.transport.loseConnection()
      return
  
    try:
      ipaddress = socket.gethostbyname(rs[0][0])
    except:
      log.msg("Can't resolve remote hub address anymore from host %s" % rs[0][0])
      self.transport.loseConnection()
      return
  
    self.game_info.host = ipaddress
    self.game_info.port = rs[0][1]
    self.game_info.remote_hub_id = server_id
    self.sendGameList(self.game_info.game_id, 0, verb)
    
  def remoteCreateGameFailure(self, failure):
    log.msg("Remote hub lookup failure: %s" % str(failure))
    self.transport.loseConnection()

  def logChat(self, message):
    if self.log_chat:
      deferred = self.dbpool.runOperation("""
        INSERT INTO chatlog
        (event_date, event_type,
         user_id, username, chatname,
         color_r, color_g, color_b,
         message)
        VALUES (NOW(), %s,
                %s, %s, %s,
                %s, %s, %s,
                %s)""",
        ('chat',
        self.user_info.user_id, self.user_info.username, self.user_info.chatname,
        self.user_info.player_info.player_color[0],
        self.user_info.player_info.player_color[1],
        self.user_info.player_info.player_color[2],
        message))
      deferred.addErrback(self.reportDbError)
  
  def logBroadcast(self, message):
    if self.log_chat:
      deferred = self.dbpool.runOperation("""
        INSERT INTO chatlog
        (event_date, event_type,
         user_id, username, chatname,
         message)
        VALUES (NOW(), %s,
                %s, %s, %s,
                %s)""",
        ('broadcast',
        self.user_info.user_id, self.user_info.username, self.user_info.chatname,
        message))
      deferred.addErrback(self.reportDbError)
  
  def logPM(self, target, message):
    if self.log_chat:
      deferred = self.dbpool.runOperation("""
        INSERT INTO chatlog
        (event_date, event_type,
         user_id, username, chatname,
         target_user_id, target_username, target_chatname,
         color_r, color_g, color_b,
         message)
        VALUES (NOW(), %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s)""",
        ('pm',
        self.user_info.user_id, self.user_info.username, self.user_info.chatname,
        target.user_id, target.username, target.chatname,
        self.user_info.player_info.player_color[0],
        self.user_info.player_info.player_color[1],
        self.user_info.player_info.player_color[2],
        message))
      deferred.addErrback(self.reportDbError)
  
  def logEvent(self, type, data=None):
    if self.log_events:
      deferred = self.dbpool.runOperation("""
        INSERT INTO eventlog
        (event_date, event_type, username, user_id, extradata)
        VALUES (NOW(), %s, %s, %s, %s)""",
        (type, self.user_info.username, self.user_id, data))
      deferred.addErrback(self.reportDbError)
  
  def logLogin(self):
    if self.log_logindetail and self.user_info.visible:
      deferred = self.dbpool.runOperation("""
        INSERT INTO logindetail
        (event_date, username, user_id, chatname,
         color_r, color_g, color_b,
         team_color_r, team_color_g, team_color_b,
         build_date, platform_type)
        VALUES(NOW(), %s, %s, %s,
               %s, %s, %s,
               %s, %s, %s,
               STR_TO_DATE(%s, "%%b %%e %%Y %%T"), %s)""",
        (self.user_info.username, self.user_id, self.user_info.chatname,
         self.user_info.player_info.player_color[0],
         self.user_info.player_info.player_color[1],
         self.user_info.player_info.player_color[2],
         self.user_info.player_info.team_color[0],
         self.user_info.player_info.team_color[1],
         self.user_info.player_info.team_color[2],
         self.user_info.player_info.build_date + b' ' + self.user_info.player_info.build_time,
         self.user_info.player_info.platform_type))
      deferred.addErrback(self.reportDbError)
  
  def reportDbError(self, failure):
    log.msg("Database failure: %s" % str(failure))
  
  def isUserIdVisible(self, user_id):
    if user_id in self.globals['users']:
      info = self.globals['users'][user_id]
      conn = info.roomd_connection
      if conn and conn.state == self.LOGGED_IN and info.visible:
        return True
    return False

  def isUserIdListening(self, user_id):
    if user_id in self.globals['users']:
      conn = self.globals['users'][user_id].roomd_connection
      if conn and conn.state == self.LOGGED_IN and not conn.deaf:
        return True
    return False

  def visibleUsersInRoom(self):
    return list(filter(lambda info: info.roomd_connection and info.roomd_connection.state == self.LOGGED_IN and info.visible, list(self.globals['users'].values())))

  def listeningUsersInRoom(self):
    return list(filter(lambda info: info.roomd_connection and info.roomd_connection.state == self.LOGGED_IN and not info.roomd_connection.deaf, list(self.globals['users'].values())))

  def userActive(self):
    if self.user_info.afk is not None:
      self.user_info.afk = None
      self.sendPlayerList(self.user_id, 0, self.VERB_CHANGE)
      self.checkRainbow()
      
  def handleChatCommand(self, messagebytes, target=None):
    if not messagebytes.startswith('.'.encode('mac_roman')):
      return False
    message = messagebytes.decode('mac_roman')
    words = message.split()
    if words[0] == ".afk":
      away_msg = "afk"
      if len(words) > 1:
        away_msg = ' '.join(words[1:])
      self.user_info.afk = away_msg.encode('mac_roman')
      self.sendPlayerList(self.user_id, 0, self.VERB_CHANGE)
      self.checkRainbow()
    elif words[0] == ".back":
      pass # userActive() already called when message came in
    elif words[0] == ".caste" or words[0] == ".info":
      if target is None:
        self.sendRoomMessage("No user selected")
      else:
        if target.username is None:
          self.sendRoomMessage(target.chatname.decode('mac_roman') + " is a guest")
        elif target.moderator:
          self.sendRoomMessage(target.chatname.decode('mac_roman') + " is the moderator \"" + target.username.decode('mac_roman') + "\"")
        else:
          self.sendRoomMessage(target.chatname.decode('mac_roman') + " is registered as \"" + target.username.decode('mac_roman') + "\"")
    elif words[0] == ".help":
      self.sendCommandHelp()
    elif words[0] == ".action" or words[0] == ".me":
      if len(words) < 2:
        self.sendRoomMessage("A message is required for " + words[0])
      else:
        cur_time = time.time()
        if cur_time < self.user_info.action_timer:
          self.sendRoomMessage("Please wait 15 seconds between " + words[0] + " commands")
        else:
          self.user_info.action_timer = cur_time + 15
          self.broadcastRoomMessage(self.user_info.chatname.decode('mac_roman') + ' ' + ' '.join(words[1:]))
    elif words[0] == ".credits" or words[0] == ".about":
      self.sendRoomMessage("Aleph One Metaserver - http://metaserver.lhowon.org/")
    elif words[0] == ".kick" and self.user_info.moderator:
      if target is None:
        self.sendRoomMessage("No user selected")
      elif target.roomd_connection:
        extra = ''
        if target.username:
          extra = ' [' + target.username.decode('mac_roman') + ']'
        self.logEvent('kick', target.chatname.decode('mac_roman') + extra)
        target.roomd_connection.transport.loseConnection()
        self.broadcastRoomMessage('Moderator ' + self.user_info.chatname.decode('mac_roman') + ' kicked ' + target.chatname.decode('mac_roman'))
    elif words[0] == ".rainbow" and self.user_info.moderator:
      if self.globals['rainbow'] is None:
        self.globals['rainbow'] = 'rainbow'
        self.checkRainbow()
      else:
        self.globals['rainbow'] = None
        self.resetColors()
    elif words[0] == ".test":
      if self.game_info is None:
        self.sendRoomMessage("You must be gathering a game to run this test.")
      elif self.tester is not None:
        self.sendRoomMessage("The test is still running, please be patient.")
      else:
        self.sendRoomMessage("Testing your network connection...")
        self.tester = GameTester(self.game_info.host, self.game_info.port)
        self.tester.setMessageCallback(self.gameTesterMessage)
        self.tester.setFinishedCallback(self.gameTesterFinished)
        self.tester.run()
    else:
      self.sendRoomMessage("Unknown command: " + words[0] + " - for command list, type: .help")
      # self.sendCommandHelp()
      
    return True
  
  def sendCommandHelp(self):
    self.sendRoomMessage("Command list:")
    self.sendRoomMessage(".about/.credits - about the server")
    self.sendRoomMessage(".action/.me [message] - narrate yourself")
    self.sendRoomMessage(".afk [away message] - set your away status")
    self.sendRoomMessage(".back - cancels .afk")
    self.sendRoomMessage(".caste/.info - info about selected user")
    self.sendRoomMessage(".test - test your ability to gather games")
    self.sendRoomMessage(".help - this list of commands")
    if self.user_info.moderator:
      self.sendRoomMessage("Moderator-only commands:")
      self.sendRoomMessage(".kick - disconnect the selected user")
      self.sendRoomMessage(".rainbow - A FRIGGIN' RAINBOW")
  
  def gameTesterMessage(self, tester, message):
    if tester == self.tester:
      self.sendRoomMessage(message)
  
  def gameTesterFinished(self, tester, success, warn):
    if tester == self.tester:
      self.tester = None
      if success:
        if warn:
          self.sendRoomMessage("Test passed with warnings. Some players will be unable to join.")
        else:
          self.sendRoomMessage("Test passed. You can gather games.")
      elif success is False:
        self.sendRoomMessage("Test failed. You cannot gather games.")

  def checkRainbow(self):
    changed = False
    if self.globals['rainbow'] == 'rainbow':
      # check if any moderators are still in the room; count visible users
      cancel = True
      num_users = 0
      for user_info in self.visibleUsersInRoom():
        if user_info.moderator:
          cancel = False
        num_users += 1
      if cancel:
        self.globals['rainbow'] = None
        self.resetColors()
        return
    
      index = 0
      for user_info in sorted(self.visibleUsersInRoom()):
        color1 = UserInfo.rainbow_for_pos(index, num_users)
        color2 = UserInfo.rainbow_for_pos(index + 1, num_users)
        if user_info.player_info.player_color != color1:
          user_info.player_info.player_color = color1
          changed = True
        if user_info.player_info.team_color != color2:
          user_info.player_info.team_color = color2
          changed = True
        index += 1
      
    if changed:
      self.sendPlayerList(0, 0, self.VERB_CHANGE)
      
  def resetColors(self):
    changed = False
    for user_info in self.visibleUsersInRoom():
      if user_info.player_info.player_color != user_info.original_player_color:
        user_info.player_info.player_color = user_info.original_player_color
        changed = True
      if user_info.player_info.team_color != user_info.original_team_color:
        user_info.player_info.team_color = user_info.original_team_color
        changed = True
      
    if changed:
      self.sendPlayerList(0, 0, self.VERB_CHANGE)

class RoomdFactory(Factory):

  def __init__(self, userd_factory, options=None):
#     Factory.__init__(self)
    self.userd_factory = userd_factory
    self.options = options
  
  def buildProtocol(self, addr):
    return Roomd(self)
