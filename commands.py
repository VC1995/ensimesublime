import sublime

from .ensimesublime.core import EnsimeWindowCommand
from .ensimesublime.launcher import EnsimeLauncher
from .ensimesublime.client import EnsimeClient


class EnsimeStartup(EnsimeWindowCommand):
    def is_enabled(self):
        # should we check self.env.valid ?
        return bool(self.env and not self.env.running)

    def run(self):
        try:
            self.env.recalc()
        except Exception as err:
            sublime.error_message(err)
        else:
            l = EnsimeLauncher(self.env.config)
            self.env.client = EnsimeClient(self.env.logger, l, self.env.connection_timeout)
            self.env.client.setup()


class EnsimeShutdown(EnsimeWindowCommand):
    def is_enabled(self):
        return bool(self.env and self.env.running)

    def run(self):
        self.env.client.teardown()
