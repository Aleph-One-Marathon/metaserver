Non-guest users are looked up by username in the `user` table. Only SELECT queries are run; no inserts or updates are done. Other fields may be added to the table.

* The `sort_order` field must be unique. An auto-incremented number is fine.
* The `username` field must be unique. The username entered in Aleph One will be checked against this field. Usernames should be ASCII, and Aleph One currently has a limit of 15 characters.
* The `password` field contains a hash created by the [phpass](http://www.openwall.com/phpass/) framework.
* The `moderator` field grants access to moderator-only commands, like `.gag` or `.kick`.
* The `hide_in_room` field, when set, prevents the user from being announced in player lists. This can be used to suppress join and leave messages from bots or system-monitoring tools.

        CREATE TABLE user (
          sort_order int,
          username varchar(255),
          password varchar(255),
          moderator boolean,
          hide_in_room boolean );

Other tables are used for logging. Only INSERT statements are run; no selects or updates are done. Other fields, such as an auto-increment ID, may be added to the tables. If logging is disabled in the config file, these tables do not need to be present.

Aleph One currently uses MacRoman character encoding for non-ASCII text. The server does no character conversion; strings are stored as-is in the database. Fields that may contain MacRoman text are designated below as `varbinary` or `blob`.

        CREATE TABLE chatlog (
          event_date datetime,
          event_type varchar(64),
          user_id int,
          username varchar(255),
          chatname varbinary(255),
          color_r int unsigned,
          color_g int unsigned,
          color_b int unsigned,
          target_user_id int,
          target_username varchar(255),
          target_chatname varbinary(255),
          message blob );
        
        CREATE TABLE eventlog (
          event_date datetime,
          event_type varchar(64),
          username varchar(255),
          user_id int,
          extradata blob );

        CREATE TABLE logindetail (
          event_date datetime,
          username varchar(255),
          user_id int,
          chatname varbinary(255),
          color_r int unsigned,
          color_g int unsigned,
          color_b int unsigned,
          team_color_r int unsigned,
          team_color_g int unsigned,
          team_color_b int unsigned,
          build_date datetime,
          platform_type int unsigned );
