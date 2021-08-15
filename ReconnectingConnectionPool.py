## The following code was retrieved from:
## http://web.archive.org/web/20101111172427/http://www.gelens.org/2009/09/13/twisted-connectionpool-revisited
##
## Copyright (C) 2009 by Jeffrey Galens

from twisted.enterprise import adbapi
from twisted.python import log
import pymysql

class ReconnectingConnectionPool(adbapi.ConnectionPool):
    """Reconnecting adbapi connection pool for MySQL.

    This class improves on the solution posted at
    http://www.gelens.org/2008/09/12/reinitializing-twisted-connectionpool/
    by checking exceptions by error code and only disconnecting the current
    connection instead of all of them.

    Also see:
    http://twistedmatrix.com/pipermail/twisted-python/2009-July/020007.html

    """
    def _runInteraction(self, interaction, *args, **kw):
        try:
            return adbapi.ConnectionPool._runInteraction(self, interaction, *args, **kw)
        except pymysql.OperationalError as e:
            # 1927: MariaDB: connection killed
            # 2006: MySQL: server has gone away
            # 2013: MySQL: lost connection during query
            if e.args[0] not in (1927, 2006, 2013):
                raise
            log.msg("RCP: got error %s, retrying operation" %(e))
            conn = self.connections.get(self.threadID())
            self.disconnect(conn)
            # try the interaction again
            return adbapi.ConnectionPool._runInteraction(self, interaction, *args, **kw)
