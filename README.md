This is a partial implementation of [Bungie](http://www.bungie.net/)'s Myth metaserver protocol, written in Python using the Twisted framework.

### Installation

* Set up a MySQL database with the tables and fields described in `database.md`.

* Edit `config.ini` with your database information, and the addresses and ports to use for the metaserver. You can use a different config file by setting the environment variable `METASERVER_CONFIG` to the file's path.

* Start the server with:

        twistd -y metaserver.tac

* Aleph One is hardcoded to connect to metaserver.lhowon.org on port 6321. To use your own metaserver, you will need to build a custom version of Aleph One, or redirect this traffic using /etc/hosts or your router or firewall.

### Limitations

The implementation is designed for use with [Aleph One](http://alephone.lhowon.org/), and only supports the subset of features actually used by Aleph One. It also trades scalability for simplicity: only one room is available, handled by the same server process as the initial user connections.

### Requirements

* Python 3 (tested with 3.7.10)
* MySQL or compatible database (tested with MariaDB 10.5.10)
* Python modules:
    * Twisted (tested with 21.7.0)
    * PyMySQL (tested with 1.0.2)
    * bcrypt (tested with 3.2.0)
    * crcmod (tested with 1.7)

### Acknowledgements

Knowledge of the protocol came from inspection of Aleph One's source code, and also from inspection of the [MythServer](http://tain.totalcodex.net/items/show/updated-metaserver-source-code) releases based on Bungie's Myth II metaserver source code. The server itself is a fresh implementation rather than a port of any existing codebase.

### Licensing

Copyright (C) 2014 and beyond by Jeremiah Morris and contributing developers.
Portions copyright (C) 2009 by Jeffrey Galens.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <http://www.gnu.org/licenses/>.
