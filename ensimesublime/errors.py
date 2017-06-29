class InvalidJavaPathError(OSError):
    """Raised when ensime-sublime cannot find a valid Java executable."""
    def __init__(self, errno, msg, filename, *args):
        super(InvalidJavaPathError, self).__init__(errno, msg, filename, *args)


class LaunchError(RuntimeError):
    """Raised when ensime-sublime cannot launch the ENSIME server."""


class DotEnsimeNotFound(OSError):
    """Raised when ensime-sublime cannot find the .ensime file."""
    def __init__(self, errno, msg, filename, *args):
        super(DotEnsimeNotFound, self).__init__(errno, msg, filename, *args)


class BadEnsimeConfig(RuntimeError):
    """Raised when .ensime file cannot be parsed."""
