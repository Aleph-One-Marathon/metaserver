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

from twisted.application import internet, service
from configparser import ConfigParser

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from Userd import UserdFactory
from Roomd import RoomdFactory
from ReconnectingConnectionPool import ReconnectingConnectionPool

def get_strings(config, section, dict, optlist):
  for opt in optlist:
    if config.has_option(section, opt):
      dict[opt] = config.get(section, opt)

def get_ints(config, section, dict, optlist):
  for opt in optlist:
    if config.has_option(section, opt):
      dict[opt] = config.getint(section, opt)

def getConfigPath():
  return os.environ.get('METASERVER_CONFIG', 'config.ini')

def getMetaService():

  ## Extra configuration
  
  config = ConfigParser()
  config.read(getConfigPath())

  ## Database setup
  
  dbopts = { 'cp_reconnect' : True }
  get_strings(config, 'mysql', dbopts, ['host', 'db', 'user', 'passwd'])
  get_ints(config, 'mysql', dbopts, ['port'])
  dbpool = ReconnectingConnectionPool("pymysql", **dbopts)
  
  ## Server setup
  
  srvopts = { 'roomd_host' : None, 'roomd_port' : 6335, 'userd_port' : 6321 }
  get_strings(config, 'ports', srvopts, ['roomd_host'])
  get_ints(config, 'ports', srvopts, ['roomd_port', 'userd_port'])
  
  othopts = { 'log_events' : 1, 'log_logindetail' : 1, 'log_chat' : 1, 'log_pm' : 1 }
  get_ints(config, 'other', othopts, ['log_events', 'log_logindetail', 'log_chat', 'log_pm'])
  
  ## Factory setup
  
  ufac = UserdFactory(srvopts['roomd_host'], srvopts['roomd_port'], othopts, dbpool)
  rfac = RoomdFactory(ufac, othopts)

  ## Service setup
  metaService = service.MultiService()
  internet.TCPServer(srvopts['userd_port'], ufac).setServiceParent(metaService)
  internet.TCPServer(srvopts['roomd_port'], rfac).setServiceParent(metaService)
  
  return metaService


application = service.Application("metaserver")
getMetaService().setServiceParent(application)
