import os
from contextlib import contextmanager


@contextmanager
def catch(exception, handler=lambda e: None):
    """If exception runs handler."""
    try:
        yield
    except exception as e:
        handler(str(e))


class Util(object):
    @staticmethod
    def read_file(path):
        with open(path, "r") as f:
            result = f.read()
        return result

    @staticmethod
    def write_file(path, contents):
        with open(path, "w") as f:
            result = f.write(contents)
        return result

    @staticmethod
    def mkdir_p(path):
        if not os.path.exists(path):
            os.makedirs(path)
