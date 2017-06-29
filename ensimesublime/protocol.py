# coding: utf-8
import sublime

from .util import catch
from .core import EnsimeCommon


class ProtocolHandler(object):
    """Mixin for common behavior of handling ENSIME protocol responses.

    Actual handler implementations are abstract and should be implemented by a
    subclass. Requires facilities of an ``EnsimeClient``.
    """

    def __init__(self, logger):
        self.handlers = {}
        self.register_responses_handlers()

    def register_responses_handlers(self):
        """Register handlers for responses from the server.

        A handler must accept only one parameter: `payload`.
        """
        self.handlers["SymbolInfo"] = self.handle_symbol_info
        self.handlers["IndexerReadyEvent"] = self.handle_indexer_ready
        self.handlers["AnalyzerReadyEvent"] = self.handle_analyzer_ready
        self.handlers["NewScalaNotesEvent"] = self.buffer_typechecks
        self.handlers["NewJavaNotesEvent"] = self.buffer_typechecks_and_display
        self.handlers["BasicTypeInfo"] = self.show_type
        self.handlers["ArrowTypeInfo"] = self.show_type
        self.handlers["FullTypeCheckCompleteEvent"] = self.handle_typecheck_complete
        self.handlers["StringResponse"] = self.handle_string_response
        self.handlers["CompletionInfoList"] = self.handle_completion_info_list
        self.handlers["TypeInspectInfo"] = self.handle_type_inspect
        self.handlers["SymbolSearchResults"] = self.handle_symbol_search
        self.handlers["DebugOutputEvent"] = self.handle_debug_output
        self.handlers["DebugBreakEvent"] = self.handle_debug_break
        self.handlers["DebugBacktrace"] = self.handle_debug_backtrace
        self.handlers["DebugVmError"] = self.handle_debug_vm_error
        self.handlers["RefactorDiffEffect"] = self.apply_refactor
        self.handlers["ImportSuggestions"] = self.handle_import_suggestions
        self.handlers["PackageInfo"] = self.handle_package_info

    def handle_incoming_response(self, call_id, payload):
        """Get a registered handler for a given response and execute it."""
        self.logger.debug('handle_incoming_response: in [typehint: %s, call ID: %s]',
                          payload['typehint'], call_id)  # We already log the full JSON response

        typehint = payload["typehint"]
        handler = self.handlers.get(typehint)

        def feature_not_supported(m):
            sublime.error_message("not supported :(")
            # msg = feedback["handler_not_implemented"]
            # sublime.error_message(msg.format(typehint, self.launcher.ensime_version))

        if handler:
            with catch(NotImplementedError, feature_not_supported):
                handler(call_id, payload)
        else:
            self.log.warning('Response has not been handled: %s', payload)

    def handle_indexer_ready(self, call_id, payload):
        raise NotImplementedError()

    def handle_analyzer_ready(self, call_id, payload):
        raise NotImplementedError()

    def handle_debug_vm_error(self, call_id, payload):
        raise NotImplementedError()

    def handle_import_suggestions(self, call_id, payload):
        raise NotImplementedError()

    def handle_package_info(self, call_id, payload):
        raise NotImplementedError()

    def handle_symbol_search(self, call_id, payload):
        raise NotImplementedError()

    def handle_symbol_info(self, call_id, payload):
        raise NotImplementedError()

    def handle_string_response(self, call_id, payload):
        raise NotImplementedError()

    def handle_completion_info_list(self, call_id, payload):
        raise NotImplementedError()

    def handle_type_inspect(self, call_id, payload):
        raise NotImplementedError()

    def show_type(self, call_id, payload):
        raise NotImplementedError()
