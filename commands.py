import sublime

from .ensimesublime.core import EnsimeWindowCommand
from .ensimesublime.launcher import EnsimeLauncher
from .ensimesublime.client import EnsimeClient


class EnsimeStartup(EnsimeWindowCommand):
    def is_enabled(self):
        # should we check self.env.valid ?
        return bool(self.env and not self.env.running)

    def run(self):
        # refreshes the config (fixes #29)
        try:
            self.env.recalc()
        except Exception as err:
            sublime.error_message(err)
        else:
            l = EnsimeLauncher(self.env.config)
            self.env.client = EnsimeClient(self.env.logger, l, self.env.connection_timeout)
            success = self.env.client.setup()
            if not success:
                self.env.logger.info("Ensime startup failed.")
            else:
                self.env.logger.info("Ensime startup complete.")


class EnsimeShutdown(EnsimeWindowCommand):
    def is_enabled(self):
        return bool(self.env and self.env.running)

    def run(self):
        self.env.client.teardown()
