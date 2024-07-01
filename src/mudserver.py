"""Basic MUD server module for creating text-based Multi-User Dungeon
(MUD) games.

Contains one class, MudServer, which can be instantiated to start a
server running then used to send and receive messages from players.

author: Mark Frimston - mfrimston@gmail.com
"""


import socket
import select
import time
import sys
import json

if 'esp' in sys.platform:
    import ustruct
else:
    import struct

from utils import get_color, get_color_list, multiple_replace


class MudServer(object):
    """A basic server for text-based Multi-User Dungeon (MUD) games.

    Once created, the server will listen for players connecting using
    Telnet. Messages can then be sent to and from multiple connected
    players.

    The 'update' method should be called in a loop to keep the server
    running.
    """

    # An inner class which is instantiated for each connected client to store
    # info about them

    class _Client(object):
        """Holds information about a connected player"""

        # the socket object used to communicate with this client
        socket = None
        # the ip address of this client
        address = ""
        # holds data send from the client until a full message is received
        buffer = ""
        # the last time we checked if the client was still connected
        lastcheck = 0

        color_enabled = True
        
        def __init__(self, socket, address, buffer, lastcheck):
            self.socket = socket
            self.address = address
            self.buffer = buffer
            self.lastcheck = lastcheck


    # Used to store different types of occurences
    _EVENT_NEW_PLAYER = 1
    _EVENT_PLAYER_LEFT = 2
    _EVENT_COMMAND = 3

    # Different states we can be in while reading data from client
    # See _process_sent_data function
    _READ_STATE_NORMAL = 1
    _READ_STATE_COMMAND = 2
    _READ_STATE_SUBNEG = 3
    _READ_NAWS = 4
    _READ_MSDP = 5

    _ECHO = 1
    _NAWS = 31
    _MSDP = 69
    _MSSP = 70
    _MXP = 91
    _GMCP = 201

    _MSSP_VAR = 1
    _MSSP_VAL = 2

    _MSDP_VAR = 1
    _MSDP_VAL = 2
    _MSDP_TABLE_OPEN = 3
    _MSDP_TABLE_CLOSE = 4
    _MSDP_ARRAY_OPEN = 5
    _MSDP_ARRAY_CLOSE = 6

    # Command codes used by Telnet protocol
    # See _process_sent_data function
    _TN_IAC = 255
    _TN_DONT = 254
    _TN_DO = 253
    _TN_WONT = 252
    _TN_WILL = 251
    _TN_SUB_START = 250
    _TN_SUB_END = 240

    # socket used to listen for new clients
    _listen_socket = None
    # holds info on clients. Maps client id to _Client object
    _clients = {}
    # counter for assigning each client a new id
    _nextid = 0
    # list of occurences waiting to be handled by the code
    _events = []
    # list of newly-added occurences
    _new_events = []

    start_time = time.time()


    def __init__(self):
        """Constructs the MudServer object and starts listening for
        new players.
        """

        self._clients = {}
        self._nextid = 0
        self._events = []
        self._new_events = []

        # create a new tcp socket which will be used to listen for new clients
        self._listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # set a special option on the socket which allows the port to be
        # immediately without having to wait
        self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind the socket to an ip address and port. Port 23 is the standard
        # telnet port which telnet clients will use, however on some platforms
        # this requires root permissions, so we use a higher arbitrary port
        # number instead: 1234. Address 0.0.0.0 means that we will bind to all
        # of the available network interfaces
        self._listen_socket.bind(("0.0.0.0", 4000))

        # set to non-blocking mode. This means that when we call 'accept', it
        # will return immediately without waiting for a connection
        self._listen_socket.setblocking(False)

        # start listening for connections on the socket
        self._listen_socket.listen(1)

    def update(self):
        """Checks for new players, disconnected players, and new
        messages sent from players. This method must be called before
        up-to-date info can be obtained from the 'get_new_players',
        'get_disconnected_players' and 'get_commands' methods.
        It should be called in a loop to keep the game running.
        """

        # check for new stuff
        self._check_for_new_connections()
        self._check_for_disconnected()
        self._check_for_messages()

        # move the new events into the main events list so that they can be
        # obtained with 'get_new_players', 'get_disconnected_players' and
        # 'get_commands'. The previous events are discarded
        self._events = list(self._new_events)
        self._new_events = []

    def get_remote_ip(self, clid):
        if 'esp' in sys.platform:
            return 'Unknown IP'
        else:
            cl = self._clients[clid]
            return cl.socket.getpeername()

    def disconnect_player(self, clid):
        cl = self._clients[clid]
        cl.socket.close()
        self._handle_disconnect(clid)

    def get_new_players(self):
        """Returns a list containing info on any new players that have
        entered the game since the last call to 'update'. Each item in
        the list is a player id number.
        """
        retval = []
        # go through all the events in the main list
        for ev in self._events:
            # if the event is a new player occurence, add the info to the list
            if ev[0] == self._EVENT_NEW_PLAYER:
                retval.append(ev[1])
        # return the info list
        return retval

    def get_disconnected_players(self):
        """Returns a list containing info on any players that have left
        the game since the last call to 'update'. Each item in the list
        is a player id number.
        """
        retval = []
        # go through all the events in the main list
        for ev in self._events:
            # if the event is a player disconnect occurence, add the info to
            # the list
            if ev[0] == self._EVENT_PLAYER_LEFT:
                retval.append(ev[1])
        # return the info list
        return retval

    def get_commands(self):
        """Returns a list containing any commands sent from players
        since the last call to 'update'. Each item in the list is a
        3-tuple containing the id number of the sending player, a
        string containing the command (i.e. the first word of what
        they typed), and another string containing the text after the
        command
        """
        retval = []
        # go through all the events in the main list
        for ev in self._events:
            # if the event is a command occurence, add the info to the list
            if ev[0] == self._EVENT_COMMAND:
                retval.append((ev[1], ev[2], ev[3]))
        # return the info list
        return retval

    def send_message(self, to, message, line_ending='\r\n', color=None, nowrap=False):
        """Sends the text in the 'message' parameter to the player with
        the id number given in the 'to' parameter. The text will be
        printed out in the player's terminal.
        """
        # we make sure to put a newline on the end so the client receives the
        # message on its own line

        try:
            color_enabled = self._clients[to].color_enabled
        except KeyError:
            color_enabled = False

        message = multiple_replace(message, get_color_list(), color_enabled)
        if nowrap:
            lines = [message]
        else:
            chunks, chunk_size = len(message), 80 #len(x)/4
            lines = [message[i:i + chunk_size] for i in range(0, chunks, chunk_size)]
        if color and self._clients[to].color_enabled:
            if isinstance(color, list):
                colors = ''.join([get_color(c) for c in color])
                self._attempt_send(to, colors + '\r\n'.join(lines) + line_ending + get_color('reset'))
            else:
                self._attempt_send(to, get_color(color) + '\r\n'.join(lines) + line_ending + get_color('reset'))
        else:
            if color_enabled:
                self._attempt_send(to, '\r\n'.join(lines) + line_ending + get_color('reset'))
            else:
                self._attempt_send(to, '\r\n'.join(lines) + line_ending)

    def shutdown(self):
        """Closes down the server, disconnecting all clients and
        closing the listen socket.
        """
        # for each client
        for cl in self._clients.values():
            # close the socket, disconnecting the client
            cl.socket.shutdown()
            cl.socket.close()
        # stop listening for new clients
        self._listen_socket.close()

    def send_room(self, clid, num, name, zone, terrain, details, exits, coords):
        if self._clients[clid].GMCP_ENABLED:
            room = 'Room.Info {"num": %i, "name":"%s","zone":"%s","terrain":"%s","details":"%s","exits":%s,"coord":%s}' % (num, name, zone, terrain, details, json.dumps(exits), json.dumps(coords))
            print(room)
            self.gmcp_message(clid, room)
        if self._clients[clid].MXP_ENABLED:
            self.mxp_secure(clid, name, 10)

    # def send_description(self, clid, description, command=''):
    #     if self._clients[clid].MXP_ENABLED:
    #         output = ""
    #         for idx, item in enumerate(list_items):
    #             if idx > 0:
    #                 output += ", "
    #             parts = item.split(' ')
    #             mod_item = item
    #             if len(parts) > 1:
    #                 try:
    #                     num = int(parts[0])
    #                     mod_item = ' '.join(parts[1:])[:-1]
    #                 except ValueError:
    #                     pass

    #             output += "<send \"{} {}\">{}</send>".format(command, mod_item, item)
    #         self.mxp_secure(clid, output)
    #     else:
    #         self.send_message(clid, ', '.join(list_items))

    def send_list(self, clid, list_items, command=''):
        if self._clients[clid].MXP_ENABLED:
            output = ""
            for idx, item in enumerate(list_items):
                if idx > 0:
                    output += ", "
                parts = item.split(' ')
                mod_item = item
                if len(parts) > 1:
                    try:
                        num = int(parts[0])
                        mod_item = ' '.join(parts[1:])[:-1]
                    except ValueError:
                        pass

                output += "<send \"{} {}\">{}</send>".format(command, mod_item, item)
            self.mxp_secure(clid, output)
        else:
            self.send_message(clid, ', '.join(list_items))

    def gmcp_message(self, clid, message):
        array = [self._TN_IAC, self._TN_SUB_START, self._GMCP]
        for char in message:
            array.append(ord(char))
        array.append(self._TN_IAC)
        array.append(self._TN_SUB_END)
        byte_data = bytearray(array)

        print("SENDING GMCP")
        print(byte_data)
        client_socket = self._clients[clid].socket
        client_socket.sendall(byte_data)

    def mxp_secure(self, clid, message, mxp_code="1"):
        if 'esp' in sys.platform:
            bytes_to_send = bytearray("\x1b[{}z{}\x1b[3z\r\n".format(mxp_code, message))
        else:
            bytes_to_send = bytearray("\x1b[{}z{}\x1b[3z\r\n".format(mxp_code, message), 'utf-8')            
        client_socket = self._clients[clid].socket
        client_socket.sendall(bytes_to_send)

    def raw_send(self, clid, bytes_to_send):
        client_socket = self._clients[clid].socket
        client_socket.sendall(bytes_to_send)

    def _attempt_send(self, clid, data):
        # python 2/3 compatability fix - convert non-unicode string to unicode
        if sys.version < '3' and type(data) != unicode:
            data = unicode(data, "latin1")
        try:
            # look up the client in the client map and use 'sendall' to send
            # the message string on the socket. 'sendall' ensures that all of
            # the data is sent in one go
            if sys.version_info != (3, 4, 0):
                bytes_to_send = bytearray(data, 'latin1')
            else:
                bytes_to_send = bytearray(data, "utf-8")
            #if len(bytes_to_send):
            #    print(bytes_to_send)
            client_socket = self._clients[clid].socket
            client_socket.sendall(bytes_to_send)
            # KeyError will be raised if there is no client with the given id in
            # the map
        except KeyError:
            pass
        # If there is a connection problem with the client (e.g. they have
        # disconnected) a socket error will be raised
        except Exception as e:
            if 'esp' not in sys.platform:
                import traceback
                traceback.print_exc()
            else:
                sys.print_exception(e)
            self._handle_disconnect(clid)

    def _check_for_new_connections(self):

        # 'select' is used to check whether there is data waiting to be read
        # from the socket. We pass in 3 lists of sockets, the first being those
        # to check for readability. It returns 3 lists, the first being
        # the sockets that are readable. The last parameter is how long to wait
        # - we pass in 0 so that it returns immediately without waiting
        rlist, wlist, xlist = select.select([self._listen_socket], [], [], 0)

        # if the socket wasn't in the readable list, there's no data available,
        # meaning no clients waiting to connect, and so we can exit the method
        # here
        if self._listen_socket not in rlist:
            return

        # 'accept' returns a new socket and address info which can be used to
        # communicate with the new client
        joined_socket, addr = self._listen_socket.accept()

        # set non-blocking mode on the new socket. This means that 'send' and
        # 'recv' will return immediately without waiting
        joined_socket.setblocking(False)


        # construct a new _Client object to hold info about the newly connected
        # client. Use 'nextid' as the new client's id number
        self._clients[self._nextid] = MudServer._Client(joined_socket, addr[0],
                                                        "", time.time())

        MSSP_REQUEST = bytearray([self._TN_IAC, self._TN_WILL, self._MSSP])
        joined_socket.sendall(MSSP_REQUEST)

        GMCP_REQUEST = bytearray([self._TN_IAC, self._TN_WILL, self._GMCP])
        joined_socket.sendall(GMCP_REQUEST)

        MXP_REQUEST = bytearray([self._TN_IAC, self._TN_WILL, self._MXP])
        joined_socket.sendall(MXP_REQUEST)

        NAWS_REQUEST = bytes([self._TN_IAC, self._TN_DO, self._NAWS])
        joined_socket.sendall(NAWS_REQUEST)

        # add a new player occurence to the new events list with the player's
        # id number
        self._new_events.append((self._EVENT_NEW_PLAYER, self._nextid))

        # add 1 to 'nextid' so that the next client to connect will get a
        # unique id number
        self._nextid += 1

    def _check_for_disconnected(self):

        # go through all the clients
        for id, cl in list(self._clients.items()):

            # if we last checked the client less than 5 seconds ago, skip this
            # client and move on to the next one
            if time.time() - cl.lastcheck < 5.0:
                continue

            # send the client an invisible character. It doesn't actually
            # matter what we send, we're really just checking that data can
            # still be written to the socket. If it can't, an error will be
            # raised and we'll know that the client has disconnected.
            self._attempt_send(id, "\x00")

            # update the last check time
            cl.lastcheck = time.time()

    def _check_for_messages(self):

        # go through all the clients
        for id, cl in list(self._clients.items()):

            # we use 'select' to test whether there is data waiting to be read
            # from the client socket. The function takes 3 lists of sockets,
            # the first being those to test for readability. It returns 3 list
            # of sockets, the first being those that are actually readable.
            rlist, wlist, xlist = select.select([cl.socket], [], [], 0)

            # if the client socket wasn't in the readable list, there is no
            # new data from the client - we can skip it and move on to the next
            # one
            if cl.socket not in rlist:
                continue

            try:
                # read data from the socket, using a max length of 4096
                data = cl.socket.recv(1024)

                # process the data, stripping out any special Telnet commands
                message = self._process_sent_data(cl, data)

                # if there was a message in the data
                if message:
                    print(message)
                    # remove any spaces, tabs etc from the start and end of
                    # the message
                    message = message.strip()

                    # separate the message into the command (the first word)
                    # and its parameters (the rest of the message)
                    command, params = (message.split(" ", 1) + ["", ""])[:2]

                    # add a command occurence to the new events list with the
                    # player's id number, the command and its parameters
                    self._new_events.append((self._EVENT_COMMAND, id,
                                             command.lower(), params))

            # if there is a problem reading from the socket (e.g. the client
            # has disconnected) a socket error will be raised
            except Exception as e:
                if 'esp' not in sys.platform:
                    import traceback
                    traceback.print_exc()
                else:
                    sys.print_exception(e)
                self._handle_disconnect(id)

    def _handle_disconnect(self, clid):

        # remove the client from the clients map
        del(self._clients[clid])

        # add a 'player left' occurence to the new events list, with the
        # player's id number
        self._new_events.append((self._EVENT_PLAYER_LEFT, clid))

    def remote_echo(self, clid, enable=True):
        if enable:
            bytes_to_send = bytearray([self._TN_IAC, self._TN_WONT, self._ECHO])
        else:
            bytes_to_send = bytearray([self._TN_IAC, self._TN_WILL, self._ECHO])
        try:
            client_socket = self._clients[clid].socket
            client_socket.sendall(bytes_to_send)
        except:
            pass

    def _send_mssp(self, client):
        byte_data = bytearray([self._TN_IAC, self._TN_SUB_START, self._MSSP, self._MSSP_VAR])
        byte_data.extend(b'PLAYERS')
        byte_data.append(self._MSSP_VAL)
        byte_data.extend(str(len(self._clients)).encode())
        byte_data.append(self._MSSP_VAR)
        byte_data.extend(b'UPTIME')
        byte_data.append(self._MSSP_VAL)
        byte_data.extend(str(time.time() - self.start_time).encode())
        byte_data.append(self._MSSP_VAR)
        byte_data.extend(b'NAME')
        byte_data.append(self._MSSP_VAL)
        byte_data.extend(b'WeeMud')
        byte_data.extend([self._TN_IAC, self._TN_SUB_END])

        print("SENDING MSSP")
        print(byte_data)
        client.socket.sendall(byte_data)

    # def _send_msdp_array(self, client, var, vals):
    #     byte_data = bytearray([self._TN_IAC, self._TN_SUB_START, self._MSDP, self._MSDP_VAR])
    #     byte_data.extend(var)
    #     byte_data.extend([self._MSDP_VAL, self._MSDP_ARRAY_OPEN])
    #     for val in vals:
    #         byte_data.append(self._MSDP_VAL)
    #         byte_data.extend(val)
    #     byte_data.extend([self._MSDP_ARRAY_CLOSE, self._TN_IAC, self._TN_SUB_END])
    #     print("SENDING ARRAY")
    #     out = ""
    #     out2 = ""
    #     for b in byte_data:
    #         out += " " + str(b)
    #         out2 += " " + chr(b)
    #     print(out)
    #     print(out2)
    #     print(byte_data.hex())
    #     client.socket.sendall(byte_data)

    def _process_sent_data(self, client, data):

        # the Telnet protocol allows special command codes to be inserted into
        # messages. For our very simple server we don't need to response to
        # any of these codes, but we must at least detect and skip over them
        # so that we don't interpret them as text data.
        # More info on the Telnet protocol can be found here:
        # http://pcmicro.com/netfoss/telnet.htm

        # start with no message and in the normal state
        message = None
        state = self._READ_STATE_NORMAL

        out = ""
        out2 = ""
        for b in data:
            out += " " + str(b)
            out2 += " " + chr(b)
        print(out)
        print(out2)
        option_data = bytearray()
        option_state = 0
        option_support = 0
        # go through the data a character at a time
        for c in data:

            # handle the character differently depending on the state we're in:

            # normal state
            if state == self._READ_STATE_NORMAL:

                # if we received the special 'interpret as command' code,
                # switch to 'command' state so that we handle the next
                # character as a command code and not as regular text data
                if c == self._TN_IAC:
                    state = self._READ_STATE_COMMAND

                # if we get a newline character, this is the end of the
                # message. Set 'message' to the contents of the buffer and
                # clear the buffer
                elif chr(c) == "\n":
                    message = client.buffer
                    client.buffer = ""

                # some telnet clients send the characters as soon as the user
                # types them. So if we get a backspace character, this is where
                # the user has deleted a character and we should delete the
                # last character from the buffer.
                elif chr(c) == "\x08":
                    client.buffer = client.buffer[:-1]

                # otherwise it's just a regular character - add it to the
                # buffer where we're building up the received message
                else:
                    client.buffer += chr(c)

            # command state
            elif state == self._READ_STATE_COMMAND:

                # the special 'start of subnegotiation' command code indicates
                # that the following characters are a list of options until
                # we're told otherwise. We switch into 'subnegotiation' state
                # to handle this
                if c == self._TN_SUB_START:
                    state = self._READ_STATE_SUBNEG

                # if the command code is one of the 'will', 'wont', 'do' or
                # 'dont' commands, the following character will be an option
                # code so we must remain in the 'command' state
                elif c in (self._TN_WILL, self._TN_WONT, self._TN_DO,
                                self._TN_DONT):
                    option_support = c
                    state = self._READ_STATE_COMMAND

                elif c == self._MXP:
                    if option_support == self._TN_DO:
                        print("MXP Enabled")
                        client.MXP_ENABLED = True
                        # Enable for mushclient "on command"
                        byte_data = bytearray([self._TN_IAC, self._TN_SUB_START, self._MXP, self._TN_IAC, self._TN_SUB_END])
                        client.socket.sendall(byte_data)
                    else:
                        print("MXP Disabled")
                        client.MXP_ENABLED = False
                    state = self._READ_STATE_NORMAL

                elif c == self._GMCP:
                    if option_support == self._TN_DO:
                        print("GMCP Enabled")
                        client.GMCP_ENABLED = True
                        # Enable for mushclient "on command"
                        byte_data = bytearray([self._TN_IAC, self._TN_SUB_START, self._MXP, self._TN_IAC, self._TN_SUB_END])
                        client.socket.sendall(byte_data)
                    else:
                        print("GMCP Disabled")
                        client.GMCP_ENABLED = False
                    state = self._READ_STATE_NORMAL

                elif c == self._MSSP:
                    if option_support == self._TN_DO:
                        self._send_mssp(client)
                    state = self._READ_STATE_NORMAL

                # elif c == self._MSDP:
                #     if option_support == self._TN_DO:
                #         client.MSDP_ENABLED = True
                #     else:
                #         client.MSDP_ENABLED = False
                #     state = self._READ_STATE_NORMAL

                # for all other command codes, there is no accompanying data so
                # we can return to 'normal' state.
                else:
                    state = self._READ_STATE_NORMAL

            # subnegotiation state
            elif state == self._READ_STATE_SUBNEG:
                    
                # if we reach an 'end of subnegotiation' command, this ends the
                # list of options and we can return to 'normal' state.
                # Otherwise we must remain in this state
                if c == self._TN_SUB_END:
                    if option_state == self._READ_NAWS:
                        height = 30
                        width = 100
                        try:
                            if 'esp' in sys.platform:
                                height, width = ustruct.unpack('>hh', option_data)
                            else:
                                height, width = struct.unpack('>hh', option_data)
                            if height > 0:
                                client.height = height
                            if width > 0:
                                client.width = width
                            print("Got NAWS Width: %d  Height: %d" % (client.width, client.height))
                        except:
                            pass
                        option_state = 0
                        option_data = bytearray()
                    # elif option_state == self._READ_MSDP:
                    #     print("GOT MSDP")
                    #     print(option_data)
                    #     if option_data[0] == self._MSDP_VAR:
                    #         var = ''
                    #         val = ''
                    #         val_started = False
                    #         for v in option_data[1:]:
                    #             print(v)
                    #             if v == self._TN_IAC:
                    #                 break
                    #             if v == self._MSDP_VAL:
                    #                 val_started = True
                    #                 continue
                    #             if val_started:
                    #                 val += chr(v)
                    #             else:
                    #                 var += chr(v)
                    #         print("VAR: " + var)
                    #         print("VAL: " + val)
                    #         if var == "LIST" and val == "COMMANDS":
                    #             vals = [b"LIST", b"REPORT", b"SEND"]
                    #             self._send_msdp_array(client, b"COMMANDS", vals)

                    state = self._READ_STATE_NORMAL

                # if c == self._MSDP:
                #     option_state = self._READ_MSDP
                #     option_data = bytearray()

                if c == self._NAWS:
                    option_state = self._READ_NAWS
                    option_data = bytearray()

                # if option_state in [self._READ_NAWS, self._READ_MSDP] and c not in [self._MSDP, self._NAWS] and c != self._TN_IAC:
                if option_state in [self._READ_NAWS] and c not in [self._NAWS] and c != self._TN_IAC:
                    option_data.append(c)

        # return the contents of 'message' which is either a string or None
        return message
