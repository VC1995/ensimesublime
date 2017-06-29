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
    need to provide a concrete one or use a ready-mixed subclass like
    ``EnsimeClientV1``.

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

    def __init__(self, logger, launcher, connection_timeout):  # noqa: C901 FIXME
        self.launcher = launcher
        self.logger = logger

        self.logger.debug('__init__: in')

        self.ws = None
        self.ensime = None
        self.ensime_server = None

        self.call_id = 0
        self.call_options = {}
        # self.refactor_id = 1
        # self.refactorings = {}
        self.server_connection_timeout = connection_timeout

        # Queue for messages received from the ensime server.
        self.queue = Queue()
        # self.suggestions = None
        # self.completion_timeout = 10  # seconds
        # self.completion_started = False

        # self.full_types_enabled = False
        """Whether fully-qualified types are displayed by inspections or not"""

        # self.toggle_teardown = True
        # self.connection_attempts = 0

        # By default, don't connect to server more than once
        self.number_try_connection = 1

        # self.debug_thread_id = None
        self.running = True
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

    def setup(self):
        """Check the classpath and connect to the server if necessary."""
        def lazy_initialize_ensime():
            if not self.ensime:
                self.logger.info("----Initialising server----")
                try:
                    self.ensime = self.launcher.launch()
                except LaunchError as err:
                    self.logger.error(err)
            return bool(self.ensime)

        def connect_when_ready(timeout):
            """Given a maximum timeout, waits for the http port to be
            written.
            Tries to connect to the websocket if it's written.
            If successfull and websocket is up and running, returns True,
            else returns False.
            """
            if not self.ws:
                while not self.ensime.is_ready() and (timeout > 0):
                    time.sleep(2)
                    timeout -= 2
                if self.ensime.is_ready():
                    self.connect_ensime_server()
                    return True
                return False
            return True

        # True if ensime is up and connection is ok, otherwise False
        self.connected = (self.running and
                          lazy_initialize_ensime() and
                          connect_when_ready(self.server_connection_timeout))
        if self.connected:
            self.logger.info("Connected to the ensime server.")
        else:
            if self.ensime:
                self.ensime.stop()
                self.logger.info("Failed to connect. Shutting down the server.")
            self.logger.info("Failed to start the server.")
        return self.connected

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
        else:
            # If it hits this, number_try_connection is 0
            disable_completely(None)

    def shutdown_server(self):
        """Shut down server if it is running.
        Does not change the client's running status."""
        self.logger.debug('shutdown_server: in')
        if self.ensime:
            self.ensime.stop()
            self.connected = False

    def teardown(self):
        """Shutdown down the client. Stop the server if connected."""
        self.logger.debug('teardown: in')
        self.running = False
        self.shutdown_server()

    # def send_at_position(self, what, useSelection, where="range"):
    #     self.log.debug('send_at_position: in')
    #     b, e = self.editor.selection_pos() if useSelection else self.editor.word_under_cursor_pos()
    #     self.log.debug('useSelection: {}, beg: {}, end: {}'.format(useSelection, b, e))
    #     self.send_at_point_req(what, self.editor.path(), b[0], b[1], e[0], e[1], where)

    # TODO: Should these be in Editor? They're translating to/from ENSIME's
    # coordinate scheme so it's debatable.

    # def set_position(self, decl_pos):
    #     """Set editor position from ENSIME declPos data."""
    #     if decl_pos["typehint"] == "LineSourcePosition":
    #         self.editor.set_cursor(decl_pos['line'], 0)
    #     else:  # OffsetSourcePosition
    #         point = decl_pos["offset"]
    #         row, col = self.editor.point2pos(point + 1)
    #         self.editor.set_cursor(row, col)

    # def get_position(self, row, col):
    #     """Get char position in all the text from row and column."""
    #     result = col
    #     self.log.debug('%s %s', row, col)
    #     lines = self.editor.getlines()[:row - 1]
    #     result += sum([len(l) + 1 for l in lines])
    #     self.log.debug(result)
    #     return result

    # def open_decl_for_inspector_symbol(self):
    #     self.log.debug('open_decl_for_inspector_symbol: in')
    #     lineno = self.editor.cursor()[0]
    #     symbol = self.editor.symbol_for_inspector_line(lineno)
    #     self.symbol_by_name([symbol])
    #     self.unqueue(should_wait=True)

    # def symbol_by_name(self, args, range=None):
    #     self.log.debug('symbol_by_name: in')
    #     if not args:
    #         self.editor.raw_message('Must provide a fully-qualifed symbol name')
    #         return

    #     self.call_options[self.call_id] = {"split": True,
    #                                        "vert": True,
    #                                        "open_definition": True}
    #     fqn = args[0]
    #     req = {
    #         "typehint": "SymbolByNameReq",
    #         "typeFullName": fqn
    #     }
    #     if len(args) == 2:
    #         req["memberName"] = args[1]
    #     self.send_request(req)

    # def complete(self, row, col):
    #     self.log.debug('complete: in')
    #     pos = self.get_position(row, col)
    #     self.send_request({"point": pos, "maxResults": 100,
    #                        "typehint": "CompletionsReq",
    #                        "caseSens": True,
    #                        "fileInfo": self._file_info(),
    #                        "reload": False})

    # def send_at_point_req(self, what, path, brow, bcol, erow, ecol, where="range"):
    #     """Ask the server to perform an operation at a given position."""
    #     beg = self.get_position(brow, bcol)
    #     end = self.get_position(erow, ecol)
    #     self.send_request(
    #         {"typehint": what + "AtPointReq",
    #          "file": path,
    #          where: {"from": beg, "to": end}})

    # def do_toggle_teardown(self, args, range=None):
    #     self.log.debug('do_toggle_teardown: in')
    #     self.toggle_teardown = not self.toggle_teardown

    # def type_check_cmd(self, args, range=None):
    #     """Sets the flag to begin buffering typecheck notes & clears any
    #     stale notes before requesting a typecheck from the server"""
    #     self.log.debug('type_check_cmd: in')
    #     self.start_typechecking()
    #     self.type_check("")
    #     self.editor.message('typechecking')

    # def en_install(self, args, range=None):
    #     """Bootstrap ENSIME server installation.

    #     Enabling the bootstrapping actually happens in the execute_with_client
    #     decorator when this is called, so this function is a no-op endpoint for
    #     the Vim command.
    #     TODO: this is confusing...
    #     """
    #     self.log.debug('en_install: in')

    # def type(self, args, range=None):
    #     useSelection = 'selection' in args
    #     self.log.debug('type: in, sel: {}'.format(useSelection))
    #     self.send_at_position("Type", useSelection)

    # def toggle_fulltype(self, args, range=None):
    #     self.log.debug('toggle_fulltype: in')
    #     self.full_types_enabled = not self.full_types_enabled

    #     if self.full_types_enabled:
    #         self.editor.message("full_types_enabled_on")
    #     else:
    #         self.editor.message("full_types_enabled_off")

    # def symbol_at_point_req(self, open_definition, display=False):
    #     opts = self.call_options.get(self.call_id)
    #     if opts:
    #         opts["open_definition"] = open_definition
    #         opts["display"] = display
    #     else:
    #         self.call_options[self.call_id] = {
    #             "open_definition": open_definition,
    #             "display": display
    #         }
    #     pos = self.get_position(*self.editor.cursor())
    #     self.send_request({
    #         "point": pos + 1,
    #         "typehint": "SymbolAtPointReq",
    #         "file": self.editor.path()})

    # def inspect_package(self, args):
    #     pkg = None
    #     if not args:
    #         pkg = Util.extract_package_name(self.editor.getlines())
    #         self.editor.message('package_inspect_current')
    #     else:
    #         pkg = args[0]
    #     self.send_request({
    #         "typehint": "InspectPackageByPathReq",
    #         "path": pkg
    #     })

    # def open_declaration(self, args, range=None):
    #     self.log.debug('open_declaration: in')
    #     self.symbol_at_point_req(True)

    # def open_declaration_split(self, args, range=None):
    #     self.log.debug('open_declaration: in')
    #     if "v" in args:
    #         self.call_options[self.call_id] = {"split": True, "vert": True}
    #     else:
    #         self.call_options[self.call_id] = {"split": True}

    #     self.symbol_at_point_req(True)

    # def symbol(self, args, range=None):
    #     self.log.debug('symbol: in')
    #     self.symbol_at_point_req(False, True)

    # def suggest_import(self, args, range=None):
    #     self.log.debug('suggest_import: in')
    #     pos = self.get_position(*self.editor.cursor())
    #     word = self.editor.current_word()
    #     req = {"point": pos,
    #            "maxResults": 10,
    #            "names": [word],
    #            "typehint": "ImportSuggestionsReq",
    #            "file": self.editor.path()}
    #     self.send_request(req)

    # def inspect_type(self, args, range=None):
    #     self.log.debug('inspect_type: in')
    #     pos = self.get_position(*self.editor.cursor())
    #     self.send_request({
    #         "point": pos,
    #         "typehint": "InspectTypeAtPointReq",
    #         "file": self.editor.path(),
    #         "range": {"from": pos, "to": pos}})

    # def doc_uri(self, args, range=None):
    #     """Request doc of whatever at cursor."""
    #     self.log.debug('doc_uri: in')
    #     self.send_at_position("DocUri", False, "point")

    # def doc_browse(self, args, range=None):
    #     """Browse doc of whatever at cursor."""
    #     self.log.debug('browse: in')
    #     self.call_options[self.call_id] = {"browse": True}
    #     self.send_at_position("DocUri", False, "point")

    # def rename(self, new_name, range=None):
    #     """Request a rename to the server."""
    #     self.log.debug('rename: in')
    #     if not new_name:
    #         new_name = self.editor.ask_input("Rename to:")
    #     self.editor.write(noautocmd=True)
    #     b, e = self.editor.word_under_cursor_pos()
    #     current_file = self.editor.path()
    #     self.editor.raw_message(current_file)
    #     self.send_refactor_request(
    #         "RefactorReq",
    #         {
    #             "typehint": "RenameRefactorDesc",
    #             "newName": new_name,
    #             "start": self.get_position(b[0], b[1]),
    #             "end": self.get_position(e[0], e[1]) + 1,
    #             "file": current_file,
    #         },
    #         {"interactive": False}
    #     )

    # def inlineLocal(self, range=None):
    #     """Perform a local inline"""
    #     self.log.debug('inline: in')
    #     self.editor.write(noautocmd=True)
    #     b, e = self.editor.word_under_cursor_pos()
    #     current_file = self.editor.path()
    #     self.editor.raw_message(current_file)
    #     self.send_refactor_request(
    #         "RefactorReq",
    #         {
    #             "typehint": "InlineLocalRefactorDesc",
    #             "start": self.get_position(b[0], b[1]),
    #             "end": self.get_position(e[0], e[1]) + 1,
    #             "file": current_file,
    #         },
    #         {"interactive": False}
    #     )

    # def organize_imports(self, args, range=None):
    #     self.editor.write(noautocmd=True)
    #     current_file = self.editor.path()
    #     self.send_refactor_request(
    #         "RefactorReq",
    #         {
    #             "typehint": "OrganiseImportsRefactorDesc",
    #             "file": current_file,
    #         },
    #         {"interactive": False}
    #     )

    # def add_import(self, name, range=None):
    #     if not name:
    #         name = self.editor.ask_input("Qualified name to import:")
    #     self.editor.write(noautocmd=True)
    #     self.send_refactor_request(
    #         "RefactorReq",
    #         {
    #             "typehint": "AddImportRefactorDesc",
    #             "file": self.editor.path(),
    #             "qualifiedName": name
    #         },
    #         {"interactive": False}
    #     )

    # def symbol_search(self, search_terms):
    #     """Search for symbols matching a set of keywords"""
    #     self.log.debug('symbol_search: in')

    #     if not search_terms:
    #         self.editor.message('symbol_search_symbol_required')
    #         return
    #     req = {
    #         "typehint": "PublicSymbolSearchReq",
    #         "keywords": search_terms,
    #         "maxResults": 25
    #     }
    #     self.send_request(req)

    # def send_refactor_request(self, ref_type, ref_params, ref_options):
    #     """Send a refactor request to the Ensime server.

    #     The `ref_params` field will always have a field `type`.
    #     """
    #     request = {
    #         "typehint": ref_type,
    #         "procId": self.refactor_id,
    #         "params": ref_params
    #     }
    #     f = ref_params["file"]
    #     self.refactorings[self.refactor_id] = f
    #     self.refactor_id += 1
    #     request.update(ref_options)
    #     self.send_request(request)

    # # TODO: preserve cursor position
    # def apply_refactor(self, call_id, payload):
    #     """Apply a refactor depending on its type."""
    #     supported_refactorings = ["Rename", "InlineLocal", "AddImport", "OrganizeImports"]

    #     if payload["refactorType"]["typehint"] in supported_refactorings:
    #         diff_filepath = payload["diff"]
    #         path = self.editor.path()
    #         bname = os.path.basename(path)
    #         target = os.path.join(self.tmp_diff_folder, bname)
    #         reject_arg = "--reject-file={}.rej".format(target)
    #         backup_pref = "--prefix={}".format(self.tmp_diff_folder)
    #         # Patch utility is prepackaged or installed with vim
    #         cmd = ["patch", reject_arg, backup_pref, path, diff_filepath]
    #         failed = Popen(cmd, stdout=PIPE, stderr=PIPE).wait()
    #         if failed:
    #             self.editor.message("failed_refactoring")
    #         # Update file and reload highlighting
    #         self.editor.edit(self.editor.path())
    #         self.editor.doautocmd('BufReadPre', 'BufRead', 'BufEnter')

    def send_request(self, request):
        """Send a request to the server."""
        self.logger.debug('send_request: in')

        message = {'callId': self.call_id, 'req': request}
        self.logger.debug('send_request: %s', message)
        self.send(json.dumps(message))

        call_id = self.call_id
        self.call_id += 1
        return call_id

    # def buffer_leave(self, filename):
    #     """User is changing of buffer."""
    #     self.log.debug('buffer_leave: %s', filename)
    #     # TODO: This is questionable, and we should use location list for
    #     # single-file errors.
    #     self.editor.clean_errors()

    # def type_check(self, filename):
    #     """Update type checking when user saves buffer."""
    #     self.log.debug('type_check: in')
    #     self.editor.clean_errors()
    #     self.send_request(
    #         {"typehint": "TypecheckFilesReq",
    #          "files": [self.editor.path()]})

    # def unqueue(self, timeout=10, should_wait=False):
    #     """Unqueue all the received ensime responses for a given file."""
    #     start, now = time.time(), time.time()
    #     wait = self.queue.empty() and should_wait

    #     while (not self.queue.empty() or wait) and (now - start) < timeout:
    #         if wait and self.queue.empty():
    #             time.sleep(0.25)
    #             now = time.time()
    #         else:
    #             result = self.queue.get(False)
    #             self.log.debug('unqueue: result received\n%s', result)
    #             if result and result != "nil":
    #                 wait = None
    #                 # Restart timeout
    #                 start, now = time.time(), time.time()
    #                 _json = json.loads(result)
    #                 # Watch out, it may not have callId
    #                 call_id = _json.get("callId")
    #                 if _json["payload"]:
    #                     self.handle_incoming_response(call_id, _json["payload"])
    #             else:
    #                 self.log.debug('unqueue: nil or None received')

    #     if (now - start) >= timeout:
    #         self.log.warning('unqueue: no reply from server for %ss', timeout)

    # def unqueue_and_display(self, filename):
    #     """Unqueue messages and give feedback to user (if necessary)."""
    #     if self.running and self.ws:
    #         self.editor.lazy_display_error(filename)
    #         self.unqueue()

    # def tick(self, filename):
    #     """Try to connect and display messages in queue."""
    #     if self.connection_attempts < 10:
    #         # Trick to connect ASAP when
    #         # plugin is  started without
    #         # user interaction (CursorMove)
    #         self.setup(True, False)
    #         self.connection_attempts += 1
    #     self.unqueue_and_display(filename)

    # def vim_enter(self, filename):
    #     """Set up EnsimeClient when vim enters.

    #     This is useful to start the EnsimeLauncher as soon as possible."""
    #     success = self.setup(True, False)
    #     if success:
    #         self.editor.message("start_message")

    # def complete_func(self, findstart, base):
    #     """Handle omni completion."""
    #     self.log.debug('complete_func: in %s %s', findstart, base)

    #     def detect_row_column_start():
    #         row, col = self.editor.cursor()
    #         start = col
    #         line = self.editor.getline()
    #         while start > 0 and line[start - 1] not in " .,([{":
    #             start -= 1
    #         # Start should be 1 when startcol is zero
    #         return row, col, start if start else 1

    #     if str(findstart) == "1":
    #         row, col, startcol = detect_row_column_start()

    #         # Make request to get response ASAP
    #         self.complete(row, col)
    #         self.completion_started = True

    #         # We always allow autocompletion, even with empty seeds
    #         return startcol
    #     else:
    #         result = []
    #         # Only handle snd invocation if fst has already been done
    #         if self.completion_started:
    #             # Unqueing messages until we get suggestions
    #             self.unqueue(timeout=self.completion_timeout, should_wait=True)
    #             suggestions = self.suggestions or []
    #             self.log.debug('complete_func: suggestions in')
    #             for m in suggestions:
    #                 result.append(m)
    #             self.suggestions = None
    #             self.completion_started = False
    #         return result

    # def _file_info(self):
    #     """Message fragment for ENSIME ``fileInfo`` field, from current file."""
    #     return {
    #         'file': self.editor.path(),
    #         'contents': self.editor.get_file_content(),
    #     }


# class EnsimeClientV1(ProtocolHandlerV1, EnsimeClient):
#     """An ENSIME client for the v1 Jerky protocol."""


# class EnsimeClientV2(ProtocolHandlerV2, EnsimeClient):
#     """An ENSIME client for the v2 Jerky protocol."""
