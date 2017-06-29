import sublime_plugin

from . import env


class EnsimeCommon(object):
    def __init__(self, window):
        self.env = env.getOrCreateNew(window)


class EnsimeWindowCommand(EnsimeCommon, sublime_plugin.WindowCommand):
    def __init__(self, window):
        super(EnsimeWindowCommand, self).__init__(window)
        self.window = window


class EnsimeTextCommand(EnsimeCommon, sublime_plugin.TextCommand):
    def __init__(self, owner):
        pass
