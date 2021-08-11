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

import struct
import socket
import time

def unpack_strings(data, num_strings=1, offset=0):
  maxp = len(data)
  p = offset
  cur_string = b''
  all_strings = []
  
  for i in range(num_strings):
    foundstring = b''
    if p < maxp:
      nextnull = data.find(b'\x00', p)
      if nextnull < 0:
        p = maxp
      else:
        foundstring = data[p:nextnull]
        p = nextnull + 1
    all_strings.append(foundstring)
  
  all_strings.append(p - offset)
  return tuple(all_strings)


class PlayerDataChunk:
  _fmt = struct.Struct('>xxHHHH2xHHH2xHH14x')
  
  @staticmethod
  def unpack_into(object, data, offset=0):
    object.away, pri_r, pri_g, pri_b, sec_r, sec_g, sec_b, object.order, object.client_version = PlayerDataChunk._fmt.unpack_from(data, offset)
    
    object.player_color = [ pri_r, pri_g, pri_b ]
    object.team_color = [ sec_r, sec_g, sec_b ]
    
    object.player_name, object.team_name, stringlen = unpack_strings(data, 2, offset + PlayerDataChunk._fmt.size)
  
class MessagePacket:
  code = 3
  _fmt = struct.Struct('>L')
  
  SYNTAX_ERROR = 0
  GAMES_NOT_ALLOWED = 1
  INVALID_VERSION = 2
  BAD_USER = 3
  NOT_LOGGED_IN = 4
  BAD_META_VERSION = 5
  USER_LOGGED_IN = 6
  UNKNOWN_GAME_TYPE = 7
  LOGIN_SUCCESSFUL = 8
  LOGOUT_SUCCESSFUL = 9
  NOT_IN_ROOM = 10
  GAME_EXISTS = 11
  ACCOUNT_LOGGED_IN = 12
  ROOM_FULL = 13
  ACCOUNT_LOCKED = 14
  NOT_SUPPORTED = 15
  
  _messages = [
    "Syntax error (unrecognized command).".encode('mac_roman'),
    "Login failed (Games not allowed at this time).".encode('mac_roman'),
    "Login failed (Invalid Game Version number).".encode('mac_roman'),
    "Login failed (Bad user or Password).".encode('mac_roman'),
    "User not logged in.".encode('mac_roman'),
    "Bad metaserver version.".encode('mac_roman'),
    "User already logged in!".encode('mac_roman'),
    "Unknown game type!".encode('mac_roman'),
    "User logged in.".encode('mac_roman'),
    "User logged out.".encode('mac_roman'),
    "Player not in a room!".encode('mac_roman'),
    "You already created a game!".encode('mac_roman'),
    "This account is already logged in!".encode('mac_roman'),
    "The desired room is full!".encode('mac_roman'),
    "Your account has been locked".encode('mac_roman'),
    "The game server for your product has been shutdown".encode('mac_roman') ]
  
  def __init__(self, which):
    self.data = self._fmt.pack(which) + self._messages[which] + b'\x00'


class LoginPacket:
  code = 100
  _fmt = struct.Struct('>HHLLHH32s32s32s32s')

  def __init__(self, data):
    self.platform_type, self.metaserver_version, self.flags, self.user_id, self.max_authentication, player_data_size, self.service_name, self.build_date, self.build_time, self.username = self._fmt.unpack_from(data)
    
    self.service_name = self.service_name.rstrip(b'\x00')
    self.build_date   = self.build_date.rstrip(b'\x00')
    self.build_time   = self.build_time.rstrip(b'\x00')
    self.username     = self.username.rstrip(b'\x00')
    
    PlayerDataChunk.unpack_into(self, data, self._fmt.size)

class PasswordResponsePacket:
  code = 109
  private = True
  _fmt = struct.Struct('>16s')

  def __init__(self, data):
    self.password_data, = self._fmt.unpack_from(data)
      
  def decode_password(self, auth_type=0, salt=b''):
    if auth_type == 0:  # plaintext
      self.password = self.password_data.rstrip(b'\x00')
    elif auth_type == 4:  # HTTPS
      self.password = self.password_data
    else:  # unrecognized
      pass

class LocalizationPacket:
  code = 115

  def __init__(self, data):
    pass  # there is data, but we don't care

class LogoutPacket:
  code = 102

  def __init__(self, data):
    pass  # should be empty

class RoomLoginPacket:
  code = 101
  _fmt = struct.Struct('>32s')
  
  def __init__(self, data):
    self.token, = self._fmt.unpack_from(data)
    self.token = self.token.rstrip(b'\x00')
    self.username, stringlen = unpack_strings(data, 1, self._fmt.size)

class PlayerDataPacket:
  code = 103
  
  def __init__(self, data):
    PlayerDataChunk.unpack_into(self, data)

class PlayerModePacket:
  code = 107
  _fmt = struct.Struct('>H')
  
  def __init__(self, data):
    self.deaf, = self._fmt.unpack_from(data)
    self.session_id = data[self._fmt.size:len(data)]

class CreateGamePacket:
  code = 104
  _fmt = struct.Struct('>H2x')
  
  def __init__(self, data):
    self.port, = self._fmt.unpack_from(data)
    self.game_data = data[self._fmt.size:len(data)]

class StartGamePacket:
  code = 114
  _fmt = struct.Struct('>l8x')
  
  def __init__(self, data):
    self.game_time, = self._fmt.unpack_from(data)

class RemoveGamePacket:
  code = 105
  
  def __init__(self, data):
    pass    # should be empty

class IncomingChatPacket:
  code = 200
  _fmt = struct.Struct('>12xH2xLL')
  
  def __init__(self, data):
    self.flags, self.sender_id, self.target_id = self._fmt.unpack_from(data)
    self.sender_name, self.message, stringlen = unpack_strings(data, 2, self._fmt.size)

class IncomingPrivateMessagePacket:
  code = 201
  private = True
  _fmt = struct.Struct('>LL12xH2xLL')
  
  def __init__(self, data):
    self.header_target_id, self.echo, self.flags, self.sender_id, self.target_id = self._fmt.unpack_from(data)
    self.sender_name, self.message, stringlen = unpack_strings(data, 2, self._fmt.size)

class IncomingKeepAlivePacket:
  code = 202
  
  def __init__(self, data):
    pass    # should be empty


class OutgoingKeepAlivePacket:
  code = 202
  data = None

class AcceptPacket:
  code = 12
  data = None

class SeedPacket:
  code = 6
  _fmt = struct.Struct('>h16s')
  
  def __init__(self, max_auth, seed):
    self.data = self._fmt.pack(max_auth, seed)

class LoginSuccessfulPacket:
  code = 7
  _fmt = struct.Struct('>L4x32s')
  
  def __init__(self, user_id, token):
    self.data = self._fmt.pack(user_id, token)

class RoomListPacket:
  code = 0
  _fmt = struct.Struct('>4x4sH14x')
  
  def __init__(self, host, port):
    self.data = self._fmt.pack(socket.inet_aton(host), port)

class RoomLoginSuccessfulPacket:
  code = 9
  _fmt = struct.Struct('>L4x')
  
  def __init__(self, user_id):
    self.data = self._fmt.pack(user_id)

class RoomMessagePacket:
  code = 10
  
  def __init__(self, message):
    self.data = message + b'\x00'

class PlayerListPacket:
  code = 1
  
  def __init__(self, player_list, verb):
    self.data = b''
    for user_info in player_list:
      self.data += user_info.roomPlayerDataChunk(verb)

class GameListPacket:
  code = 2
  
  def __init__(self, game_list, verb):
    self.data = b''
    for game_info in game_list:
      self.data += game_info.dataChunk(verb)

class OutgoingChatPacket:
  code = 200
  _fmt = struct.Struct('>HHHHH2xH2xLL')
  
  def __init__(self, user_info, message):
    chatname = user_info.chatname
    color = user_info.player_info.player_color
    self.data = self._fmt.pack(0, 26 + len(chatname) + len(message), color[0], color[1], color[2], 0, user_info.user_id, 0) + chatname + b'\x00' + message + b'\x00'

class OutgoingPrivateMessagePacket:
  code = 201
  _fmt = struct.Struct('>LLHHHHH2xH2xLL')
  
  def __init__(self, user_info, target_id, message):
    chatname = user_info.chatname
    color = user_info.player_info.player_color
    self.data = self._fmt.pack(target_id, 1, 0, 26 + len(chatname) + len(message), color[0], color[1], color[2], 1, user_info.user_id, target_id) + chatname + b'\x00' + message + b'\x00'
