import asyncio
import logging

import hangups
import hangups.auth

from . import irc, util, ircgateway

logger = logging.getLogger(__name__)


class Server(object):

    def __init__(self, host='localhost', port='6667', cookies=None):
        self.clients = {}
        self._hangups = hangups.Client(cookies)
        self._hangups.on_connect.add_observer(self._on_hangups_connect)

    def run(self, host, port):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            asyncio.start_server(self._on_client_connect, host=host, port=port)
        )
        logger.info('Waiting for hangups to connect...')
        loop.run_until_complete(self._hangups.connect())

    # Hangups Callbacks

    def _on_hangups_connect(self, initial_data):
        """Called when hangups successfully auths with hangouts."""
        self._user_list = hangups.UserList(
            self._hangups, initial_data.self_entity, initial_data.entities,
            initial_data.conversation_participants
        )
        self._conv_list = hangups.ConversationList(
            self._hangups, initial_data.conversation_states, self._user_list,
            initial_data.sync_timestamp
        )
        self._conv_list.on_event.add_observer(self._on_hangups_event)
        logger.info('Hangups connected. Connect your IRC clients!')

    def _on_hangups_event(self, conv_event):
        """Called when a hangups conversation event occurs."""
        if isinstance(conv_event, hangups.ChatMessageEvent):
            conv = self._conv_list.get(conv_event.conversation_id)
            user = conv.get_user(conv_event.user_id)
            sender = util.get_nick(user)
            hostmask = util.get_hostmask(user)
            channel = util.conversation_to_channel(conv)
            message = conv_event.text
            print(hostmask+' -> '+channel+' : '+conv_event.text)
            if len(conv.users) < 3:
                return


            for client in self.clients.values():
                if not channel in client.channels:
                    client.dojoin(channel)
                if message in client.sent_messages and sender == client.nickname:
                    client.sent_messages.remove(message)
#                    client.privmsg(hostmask, channel, conv_event.text)
                elif sender == client.nickname:
                    client.privmsg(hostmask, channel, conv_event.text)
                else:
                    client.privmsg(hostmask, channel, conv_event.text)

    # Client Callbacks

    def _on_client_connect(self, client_reader, client_writer):
        """Called when an IRC client connects."""
        client = ircgateway.IRCGateway(client_reader, client_writer)
        client._conv_list = self._conv_list
        client._user_list = self._user_list
        client._hangups = self._hangups
        client.connectionMade()

        task = asyncio.Task(self._handle_client(client))
        self.clients[task] = client
        logger.info("New Connection")
        task.add_done_callback(self._on_client_lost)

    def _on_client_lost(self, task):
        """Called when an IRC client disconnects."""
        self.clients[task].writer.close()
        del self.clients[task]
        logger.info("End Connection")

    @asyncio.coroutine
    def _handle_client(self, client):
        username = None
        welcomed = False

        while True:
            line = yield from client.readline()


            if not line:
                logger.info("Connection lost")
                break

            line = line.decode('utf-8','ignore').strip('\r\n')
            logger.info('Received: %r', line)

            client.dataReceived(line)

            if not welcomed and client.nickname and client.username:
                welcomed = True
                client.nick(client.nickname, util.get_nick(self._user_list._self_user))
                client.nickname = util.get_nick(self._user_list._self_user)
                client.welcome()

            continue



