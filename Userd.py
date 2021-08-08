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
from twisted.internet import reactor
from twisted.python import log
from MetaProtocol import MetaProtocol
from MetaPackets import *
from GameInfo import GameInfo
from UserInfo import UserInfo
import uuid
import os
import phpass

def inc_wrap(num, min, max):
  if num >= max:
    return min
  return num + 1

class Userd(MetaProtocol):

  TOKEN_TIMEOUT = 15
  NEED_LOGIN = 0
  NEED_PASSWORD = 1
  NEED_PWHASH = 2
  NEED_VERSION = 3
  LOGGED_IN = 4
  
  _hasher = phpass.PasswordHash(8, False)
  
  def __init__(self, factory, roomd_host=None, roomd_port=6335, dbpool=None):
    MetaProtocol.__init__(self)
    self.factory = factory
    self.globals = factory.globals
    self.roomd_host = roomd_host
    self.roomd_port = roomd_port
    self.dbpool = dbpool
  
  def connectionMade(self):
    MetaProtocol.connectionMade(self)
    self.state = self.NEED_LOGIN
    self.user_id, self.token = self.factory.buildUserID(self)
    self.user_info = self.globals['users'][self.user_id]
    if self.roomd_host is None:
      self.roomd_host = self.transport.getHost().host
  
  def packetReceived(self, packet):
    # self.factory.debugGlobals()
  
    if isinstance(packet, LoginPacket):
      return self.handleLoginPacket(packet)
    if isinstance(packet, PasswordResponsePacket):
      return self.handlePasswordResponsePacket(packet)
    if isinstance(packet, LocalizationPacket):
      return self.handleLocalizationPacket(packet)
    if isinstance(packet, LogoutPacket):
      return self.handleLogoutPacket(packet)
    return False
  
  def handleLoginPacket(self, packet):
    if self.state != self.NEED_LOGIN:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    
    self.user_info.set_player_info(packet)
    if packet.username == 'guest' or packet.username == '':
      self.user_info.chatname = '|iGuest|p ' + packet.player_name
      self.state = self.NEED_VERSION
      self.sendPacket(AcceptPacket())
    else:
      if packet.username in self.globals['usernames']:
        self.sendMessage(MessagePacket.USER_LOGGED_IN)
        return False
      self.globals['usernames'][packet.username] = self.user_id
      self.user_info.username = packet.username
      self.user_info.chatname = packet.player_name
      self.state = self.NEED_PASSWORD
      self.seed = os.urandom(16)
      self.seed_auth = 0
      if packet.max_authentication >= 4:
        self.seed_auth = 4
      self.sendPacket(SeedPacket(self.seed_auth, self.seed))
    return True
  
  def handlePasswordResponsePacket(self, packet):
    if self.state != self.NEED_PASSWORD:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    packet.decode_password(self.seed_auth, self.seed)
    self.state = self.NEED_PWHASH
    if self.seed_auth == 0:
      deferred = self.dbpool.runQuery("SELECT password, hide_in_room, moderator, sort_order FROM user WHERE BINARY username = %s", (self.user_info.username,))
      deferred.addCallback(self.passwordLookupResult, packet.password)
      deferred.addErrback(self.passwordLookupFailure)
    elif self.seed_auth == 4:
      deferred = self.dbpool.runQuery("SELECT meta_login_token, meta_login_token_date + INTERVAL 60 SECOND > NOW(), hide_in_room, moderator, sort_order FROM user WHERE BINARY username = %s", (self.user_info.username,))
      deferred.addCallback(self.passwordTokenResult, packet.password)
      deferred.addErrback(self.passwordLookupFailure)
    else:
      print "Authentication type not handled: %s" % self.seed_auth
      return False
    return True
  
  def passwordTokenResult(self, rs, saved_pw):
    if self.state != self.NEED_PWHASH:
      print "Password lookup called in wrong context"
      self.transport.loseConnection()
      return
    if len(rs) < 1:
      print "Username not found in database: %s" % self.user_info.username
      self.sendMessage(MessagePacket.BAD_USER)
      self.transport.loseConnection()
      return
    if rs[0][0] != saved_pw:
      print "Password check failed for %s" % self.user_info.username
      self.sendMessage(MessagePacket.BAD_USER)
      self.transport.loseConnection()
      return
    if not rs[0][1]:
      print "Token out of date for %s" % self.user_info.username
      self.sendMessage(MessagePacket.BAD_USER)
      self.transport.loseConnection()
      return
    print "Password accepted for %s" % self.user_info.username
    self.dbpool.runOperation("UPDATE user SET meta_login_token = NULL, meta_login_token_date = NULL WHERE BINARY username = %s", (self.user_info.username,))
    self.state = self.NEED_VERSION
    if rs[0][2]:
      self.user_info.visible = False
    if rs[0][3]:
      self.user_info.moderator = True
    if rs[0][4]:
      self.user_info.sort_id = rs[0][4]
    self.sendPacket(AcceptPacket())
  
  def passwordLookupResult(self, rs, saved_pw):
    if self.state != self.NEED_PWHASH:
      print "Password lookup called in wrong context"
      self.transport.loseConnection()
      return
    if len(rs) < 1:
      print "Username not found in database: %s" % self.user_info.username
      self.sendMessage(MessagePacket.BAD_USER)
      self.transport.loseConnection()
      return
    if not self._hasher.check_password(saved_pw, rs[0][0]):
      print "Password check failed for %s" % self.user_info.username
      self.sendMessage(MessagePacket.BAD_USER)
      self.transport.loseConnection()
      return
    print "Password accepted for %s" % self.user_info.username
    self.state = self.NEED_VERSION
    if rs[0][1]:
      self.user_info.visible = False
    if rs[0][2]:
      self.user_info.moderator = True
    if rs[0][3]:
      self.user_info.sort_id = rs[0][3]
    self.sendPacket(AcceptPacket())
  
  def passwordLookupFailure(self, failure):
    print "Password lookup failure:\n%s" % str(failure)
    self.transport.loseConnection()
  
  def handleLocalizationPacket(self, packet):
    if self.state != self.NEED_VERSION:
      self.sendMessage(MessagePacket.SYNTAX_ERROR)
      return False
    self.state = self.LOGGED_IN
    self.globals['tokens'][self.token]['active'] = True
    self.sendPacket(LoginSuccessfulPacket(self.user_id, self.token))
    self.sendPacket(RoomListPacket(self.roomd_host, self.roomd_port))
    return True
  
  def handleLogoutPacket(self, packet):
    self.factory.expireToken(self.token)
    return False
  
  def connectionLost(self, reason):
    MetaProtocol.connectionLost(self, reason)
    if self.user_id in self.globals['users']:
      uinfo = self.globals['users'][self.user_id]
      uinfo.userd_connection = None
      token = uinfo.token
      if self.state == self.LOGGED_IN:
        # give client time to connect to roomd
        reactor.callLater(self.TOKEN_TIMEOUT, self.factory.expireToken, token)
      else:
        self.factory.expireToken(token)
        self.factory.cleanUser(self.user_id)
    self.factory.debugGlobals()

class UserdFactory(Factory):
  MIN_USER_ID = 10000
  MAX_USER_ID = 60000
  MIN_GAME_ID = 10000
  MAX_GAME_ID = 60000
  
  def __init__(self, roomd_host=None, roomd_port=6335, options=None, dbpool=None):
#     Factory.__init__(self)
    self.globals = {
      'users': {},
      'tokens' : {},
      'usernames' : {},
      'games' : {},
      'rainbow' : None }
    self.last_user_id = 10000
    self.last_game_id = 40000
    self.roomd_host = roomd_host
    self.roomd_port = roomd_port
    self.options = options
    self.dbpool = dbpool
  
  def buildProtocol(self, addr):
    return Userd(self, self.roomd_host, self.roomd_port, self.dbpool)
  
  def expireToken(self, token):
    tokeninfo = self.globals['tokens'].pop(token, None)
    if tokeninfo is not None:
      uid = tokeninfo['user_id']
      if uid in self.globals['users']:
        self.globals['users'][uid].token = None
        self.cleanUser(uid)

  def redeemToken(self, token):
    tokeninfo = self.globals['tokens'].pop(token, None)
    self.debugGlobals()
    if tokeninfo is not None:
      uid = tokeninfo['user_id']
      if uid in self.globals['users']:
        self.globals['users'][uid].token = None
      if tokeninfo['active']:
        return uid
    return None

  def expireGame(self, game_id):
    gameinfo = self.globals['games'].pop(game_id, None)
    if gameinfo is not None:
      uid = gameinfo.user_id
      if uid in self.globals['users']:
        self.globals['users'][uid].game = None

  def cleanUser(self, user_id):
    if user_id in self.globals['users']:
      uinfo = self.globals['users'][user_id]
      if uinfo.userd_connection is None and uinfo.roomd_connection is None and uinfo.token is None:
        if uinfo.username in self.globals['usernames']:
          del self.globals['usernames'][uinfo.username]
        self.expireGame(uinfo.game)
        del self.globals['users'][user_id]
  
  def buildUserID(self, connection):
    uid = inc_wrap(self.last_user_id, self.MIN_USER_ID, self.MAX_USER_ID)
    while uid in self.globals['users']:
      uid = inc_wrap(uid, self.MIN_USER_ID, self.MAX_USER_ID)
    self.last_user_id = uid    

    token = self.buildToken(uid)
    self.globals['users'][uid] = UserInfo(uid, connection, token)
    return uid, token

  def buildGameID(self, user_id):
    gid = inc_wrap(self.last_game_id, self.MIN_GAME_ID, self.MAX_GAME_ID)
    while gid in self.globals['games']:
      gid = inc_wrap(gid, self.MIN_GAME_ID, self.MAX_GAME_ID)
    self.last_game_id = gid
    
    self.globals['games'][gid] = GameInfo(gid, user_id)
    self.globals['users'][user_id].game = gid
    return gid
  
  def buildToken(self, user_id):
    # TODO: convince GvR to give us do-while
    token = uuid.uuid4().hex
    while token in self.globals['tokens']:
      token = uuid.uuid4().hex
    self.globals['tokens'][token] = {
      'active' : False,
      'user_id' : user_id }
    return token
  
  def debugGlobals(self):
    
    numTokens = 0
    numActiveTokens = 0
    for k, v in self.globals['tokens'].iteritems():
      numTokens += 1
      if v['active']:
        numActiveTokens += 1
      if not v['user_id'] in self.globals['users']:
        log.msg("Bad user id %d for token %s" % (v['user_id'], k))
    log.msg("%d tokens (%d active)" % (numTokens, numActiveTokens))
    
    numUsernames = 0
    for k, v in self.globals['usernames'].iteritems():
      numUsernames += 1
      if not v in self.globals['users']:
        log.msg("Bad user id %d for username %s" % (v, k))
    log.msg("%d usernames" % numUsernames)
    
    numGames = 0
    numActiveGames = 0
    for k, ginfo in self.globals['games'].iteritems():
      numGames += 1
      if ginfo.start_time:
        numActiveGames += 1
      if not ginfo.user_id in self.globals['users']:
        log.msg("Bad user id %d for game %s" % (ginfo.user_id, k))
    log.msg("%d games (%d active)" % (numGames, numActiveGames))
    
    numUsers = 0
    numInUserd = 0
    numInRoomd = 0
    numRegistered = 0
    seen_usernames = {}
    for k, uinfo in self.globals['users'].iteritems():
      numUsers += 1
      if uinfo.userd_connection:
        numInUserd += 1
      if uinfo.roomd_connection:
        numInRoomd += 1
      if uinfo.username:
        name = uinfo.username
        numRegistered += 1
        if not name in self.globals['usernames']:
          log.msg("Unregistered username %s for user id %d" % (name, k))
        if name in seen_usernames:
          log.msg("Duplicate username %s for user id %d" % (name, k))
        seen_usernames[name] = k
    log.msg("%d users (%d in userd, %d in roomd, %d named)" % (numUsers, numInUserd, numInRoomd, numRegistered))
      
  
    
      
    
    
