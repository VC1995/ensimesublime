import os
import errno

from . import paths, sexp
from .errors import DotEnsimeNotFound, BadEnsimeConfig


def _locations(window):
    """Intelligently guess the appropriate .ensime file locations for the
    given window. Return: list of possible locations."""
    return [(f + os.sep + ".ensime") for f in window.folders() if os.path.exists(f + os.sep + ".ensime")]


def load(window):
    """Intelligently guess the appropriate .ensime file location for the
    given window. Load the .ensime and parse as s-expression.
    Return: (inferred project root directory, config sexp)
    """
    for f in _locations(window):
        root = paths.encode_path(os.path.dirname(f))
        with open(f) as open_file:
            src = open_file.read()
        try:
            conf = sexp.read_relaxed(src)
            m = sexp.sexp_to_key_map(conf)
            if m.get(":root-dir"):
                root = m[":root-dir"]
            else:
                conf = conf + [sexp.key(":root-dir"), root]
            return (root, conf)
        except Exception:
            exc_type, exc_val, _ = os.sys.exc_info()
            raise BadEnsimeConfig("""Ensime has failed to parse the .ensime configuration file at
{loc} because ofthe following error:
{typ} : {val}""".format(loc=str(f), typ=str(exc_type), val=str(exc_val)))
    raise DotEnsimeNotFound(errno.ENOENT,
                            """Ensime has failed to find a .ensime file within this project.
Create a .ensime file by running'sbt ensimeConfig' or equivalent for your build tool.\n""",
                            window.folders())
