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

class UserInfo:

  def __init__(self, uid, connection, token):
    self.user_id = uid
    self.sort_id = None
    self.userd_connection = connection
    self.roomd_connection = None
    self.username = None
    self.chatname = None
    self.game = None
    self.player_info = None
    self.visible = True
    self.in_game = False
    self.afk = None
    self.moderator = False
    self.action_timer = -1
    self.token = token
    
  def away_status(self):
    return 1 if (self.in_game or self.afk) else 0
  
  def flags(self):
    flags = 0
    if not self.away_status():
      flags += 1 << 14
    if self.moderator:
      flags += 1 << 12
    if self.username is not None:
      flags += 1 << 0
    return flags
  
  def teamname(self):
    teamname = self.username
    if teamname is None:
      teamname = ''
    return teamname
  
  def roomPlayerDataChunk(self, verb):
    _fmt = struct.Struct('>HH4xL6xH6xHHHH2xHHH20x')
    
    chatname = self.chatname
    teamname = self.teamname()

    color = self.player_info.player_color
    team = self.player_info.team_color
    
    if not self.in_game and self.afk is not None:
      chatname = '|i' + self.afk + '|p-' + chatname
    
    return _fmt.pack(verb, self.flags(), self.user_id, 40 + len(chatname) + len(teamname), self.away_status(), color[0], color[1], color[2], team[0], team[1], team[2]) + chatname + '\x00' + teamname + '\x00'
  
  def __cmp__(self, other):
    return cmp(other.flags(), self.flags()) or cmp(other.away_status(), self.away_status()) or cmp(self.user_id, other.user_id)
