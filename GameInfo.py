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
import socket
import time

class GameInfo:

  def __init__(self, gid, user_id):
    self.game_id = gid
    self.start_time = None
    self.time_left = None
    self.user_id = user_id
    self.host = None
    self.port = None
    self.visible = True
    self.game_data = None
    
  def dataChunk(self, verb):
    _fmt = struct.Struct('>L4sHBxlLH10x')
    
    game_data = self.game_data
    gametime = -1
    if self.time_left is not None:
      gametime = self.time_left
      if self.start_time is not None:
        gametime -= time.time() - self.start_time
    
    return _fmt.pack(self.game_id, socket.inet_aton(self.host), self.port, verb, int(gametime), self.user_id, len(game_data)) + game_data
