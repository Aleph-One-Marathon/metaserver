Non-guest users are looked up by username in the `user` table. Only SELECT queries are run; no inserts or updates are done. Other fields may be added to the table.

The `username` field must be unique. The `password` field contains a hash created by the [phpass](http://www.openwall.com/phpass/) framework. When the `hide_in_room` field is set, the user will not be announced in player lists; this can be used to suppress join and leave messages from bots or system-monitoring tools.

        CREATE TABLE user (
          username varchar(255),
          password varchar(255),
          hide_in_room boolean );

Two other tables are used for logging. Only INSERT statements are run; no selects or updates are done. Other fields, such as an auto-increment ID, may be added to the tables. If logging is disabled in the config file, these tables do not need to be present.

        CREATE TABLE chatlog (
          event_date datetime,
          username varchar(255),
          chatname varchar(255),
          color_r int unsigned,
          color_g int unsigned,
          color_b int unsigned,
          message text );
        
        CREATE TABLE eventlog (
          event_date datetime,
          event_type varchar(64),
          username varchar(255),
          user_id int,
          extradata text );
