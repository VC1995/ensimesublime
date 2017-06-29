# coding: utf-8
import sublime

import sys
import time
import json
from threading import Thread

import websocket

from .protocol import ProtocolHandler
from .util import catch
from .errors import LaunchError

# Queue depends on python version
if sys.version_info > (3, 0):
    from queue import Queue
else:
    from Queue import Queue


class EnsimeClient(ProtocolHandler):
    """An ENSIME client for a project configuration path (``.ensime``).

    This is a base class with an abstract ProtocolHandler – you will
    need to provide a concrete one.

    Once constructed, a client instance can either connect to an existing
    ENSIME server or launch a new one with a call to the ``setup()`` method.

    Communication with the server is done over a websocket (`self.ws`). Messages
    are sent to the server in the calling thread, while messages are received on
    a separate background thread and enqueued in `self.queue` upon receipt.

    Each call to the server contains a `callId` field with an integer ID,
    generated from `self.call_id`. Responses echo back the `callId` field so
    that appropriate handlers can be invoked.

    Responses also contain a `typehint` field in their `payload` field, which
    contains the type of the response. This is used to key into `self.handlers`,
    which stores the a handler per response type.
    """

    def __init__(self, logger, launcher, connection_timeout):
        self.launcher = launcher
        self.logger = logger

        self.logger.debug('__init__: in')

        self.ws = None
        self.ensime = None
        self.ensime_server = None

        self.call_id = 0
        self.call_options = {}
        self.connection_timeout = connection_timeout

        # Queue for messages received from the ensime server.
        self.queue = Queue()
        # By default, don't connect to server more than once
        self.number_try_connection = 1

        self.running = False
        self.connected = False

        thread = Thread(name='queue-poller', target=self.queue_poll)
        thread.daemon = True
        thread.start()

    def queue_poll(self, sleep_t=0.5):
        """Put new messages on the queue as they arrive. Blocking in a thread.

        Value of sleep is low to improve responsiveness.
        """
        connection_alive = True

        while self.running:
            if self.ws:
                def logger_and_close(msg):
                    self.logger.error('Websocket exception', exc_info=True)
                    if not self.running:
                        # Tear down has been invoked
                        # Prepare to exit the program
                        connection_alive = False  # noqa: F841
                    else:
                        if not self.number_try_connection:
                            # Stop everything.
                            self.teardown()
                            self._display_ws_warning()

                with catch(websocket.WebSocketException, logger_and_close):
                    result = self.ws.recv()
                    self.queue.put(result)

            if connection_alive:
                time.sleep(sleep_t)

    def connect_when_ready(self, timeout, fallback):
        """Given a maximum timeout, waits for the http port to be
        written.
        Tries to connect to the websocket if it's written.
        """
        if not self.ws:
            while not self.ensime.is_ready() and (timeout > 0):
                time.sleep(1)
                timeout -= 1
            if self.ensime.is_ready():
                self.connected = self.connect_ensime_server()
                self.logger.info("Connected to the server.")
            else:
                fallback()
                self.logger.info("Couldn't connect to the server waited to long :(")
        else:
            self.logger.info("Already connected.")

    def setup(self):
        """Check the classpath and connect to the server if necessary."""
        def initialize_ensime():
            if not self.ensime:
                self.logger.info("----Initialising server----")
                try:
                    self.ensime = self.launcher.launch()
                except LaunchError as err:
                    self.logger.error(err)
            return bool(self.ensime)

        # True if ensime is up, otherwise False
        self.running = initialize_ensime()
        if self.running:
            connect_when_ready_thread = Thread(target=self.connect_when_ready,
                                               args=(self.connection_timeout, self.shutdown_server))
            connect_when_ready_thread.daemon = True
            connect_when_ready_thread.start()

        return self.running

    def _display_ws_warning(self):
        warning = "A WS exception happened, 'ensime-sublime' has been disabled. " +\
            "For more information, have a look at the logs in `.ensime_cache`"
        sublime.error_message(warning)

    def send(self, msg):
        """Send something to the ensime server."""
        def reconnect(e):
            self.logger.error('send error, reconnecting...')
            self.connect_ensime_server()
            if self.ws:
                self.ws.send(msg + "\n")

        self.logger.debug('send: in')
        if self.running and self.ws:
            with catch(websocket.WebSocketException, reconnect):
                self.logger.debug('send: sending JSON on WebSocket')
                self.ws.send(msg + "\n")

    def connect_ensime_server(self):
        """Start initial connection with the server."""
        self.logger.debug('connect_ensime_server: in')

        def disable_completely(e):
            if e:
                self.logger.error('connection error: %s', e, exc_info=True)
            self.shutdown_server()
            self.logger.info("Server was shutdown.")
            self._display_ws_warning()

        if self.running and self.number_try_connection:
            self.number_try_connection -= 1
            if not self.ensime_server:
                port = self.ensime.http_port()
                uri = "websocket"
                self.ensime_server = "ws://127.0.0.1:{}/{}".format(port, uri)
            with catch(websocket.WebSocketException, disable_completely):
                # Use the default timeout (no timeout).
                options = {"subprotocols": ["jerky"]}
                options['enable_multithread'] = True
                self.logger.info("About to connect to %s with options %s",
                                 self.ensime_server, options)
                self.ws = websocket.create_connection(self.ensime_server, **options)
            if self.ws:
                self.send_request({"typehint": "ConnectionInfoReq"})
            return True
        else:
            # If it hits this, number_try_connection is 0
            disable_completely(None)
            return False

    def shutdown_server(self):
        """Shut down server if it is running.
        Does not change the client's running status."""
        self.logger.debug('shutdown_server: in')
        if self.ensime:
            self.ensime.stop()
            self.connected = False
            self.running = False

    def teardown(self):
        """Shutdown down the client. Stop the server if connected."""
        self.logger.debug('teardown: in')
        self.running = False
        self.shutdown_server()

    def send_request(self, request):
        """Send a request to the server."""
        self.logger.debug('send_request: in')

        message = {'callId': self.call_id, 'req': request}
        self.logger.debug('send_request: %s', message)
        self.send(json.dumps(message))

        call_id = self.call_id
        self.call_id += 1
        return call_id
