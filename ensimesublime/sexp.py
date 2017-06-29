class Keyword:
    def __init__(self, s):
        self.val = s

    def __repr__(self):
        return self.val

    def __eq__(self, k):
        return type(k) == type(self) and self.val == k.val


class Symbol:
    def __init__(self, s):
        self.val = s

    def __repr__(self):
        return self.val

    def __eq__(self, k):
        return type(k) == type(self) and self.val == k.val


def sexp_to_key_map(sexp):
    try:
        key_type = type(key(":key"))
        result = {}
        for i in range(0, len(sexp), 2):
            k, val = sexp[i], sexp[i + 1]
            if type(k) == key_type:
                # drop the starting ":"
                key_string = str(k)
                key_string = key_string[1:]
                result[key_string] = val
        return result
    except:
        raise TypeError("not a sexp: {s}".format(s=sexp))


def key(s):
    return Keyword(s)


def sym(s):
    return Symbol(s)


def read(s):
    """Read a sexp expression from a string."""
    return _read_form(s)[0]


def read_relaxed(s):
    """Read a sexp expression from a string.
    Unlike `read` this function allows ; comments
    and is more forgiving w.r.t whitespaces."""
    lines = s.splitlines()
    lines = [line.strip() for line in lines]
    lines = [line for line in lines if line]
    lines = [line for line in lines if not line.startswith(";")]
    s = '\n'.join(lines)
    return _read_form(s)[0]


def _read_form(form):
    """Read a form."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading form')
    ch = form[0]
    if ch.isspace():
        raise SyntaxError('unexpected whitespace while reading form')
    elif ch == '(':
        return _read_list(form)
    elif ch == '"':
        return _read_string(form)
    elif ch == ':':
        return _read_keyword(form)
    elif ch.isdigit() or ch == "-":
        return _read_int(form)
    elif ch.isalpha():
        return _read_symbol(form)
    elif ch == '\'':
        return _read_atom(form)
    else:
        raise SyntaxError('unexpected character in _read_form: ' + ch)


def _read_list(form):
    """Read a list from a string."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading list')
    if form[0] != '(':
        raise SyntaxError('expected ( as first char of list: ' + form)
    form = form[1:]
    lst = []
    while len(form) > 0:
        ch = form[0]
        if ch.isspace():
            form = form[1:]
            continue
        elif ch == ')':
            return (lst, form[1:])
        else:
            val, remain = _read_form(form)
            lst.append(val)
            form = remain
    raise SyntaxError('EOF while reading list')


def _read_string(form):
    """Read a string."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading string')
    if form[0] != '"':
        raise SyntaxError('expected ( as first char of string: ' + form)
    form = form[1:]
    s = ""
    escaped = False
    while len(form) > 0:
        ch = form[0]
        if ch == '"' and not escaped:
            return (s, form[1:])
        elif escaped:
            escaped = False
            s = s[:-1]  # remove the escaping backslash
        elif ch == "\\":
            escaped = True
        s = s + ch
        form = form[1:]
    raise SyntaxError('EOF while reading string')


def _read_atom(form):
    """Read an atom."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading atom')
    if form[0] != '\'':
        raise SyntaxError('expected \' as first char of atom: ' + form)
    form = form[1:]
    s = ""
    while len(form) > 0:
        ch = form[0]
        if ch.isspace():
            return (s, form[1:])
        s = s + ch
        form = form[1:]
    raise SyntaxError('EOF while reading atom')


def _read_keyword(form):
    """Read a keyword."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading keyword')
    if form[0] != ':':
        raise SyntaxError('expected : as first char of keyword')
    form = form[1:]
    s = ""
    while len(form) > 0:
        ch = form[0]
        if not (ch.isalpha() or ch.isdigit() or ch == '-' or ch == '.'):
            return (Keyword(":" + s), form)
        else:
            s = s + ch
            form = form[1:]

    if len(s) > 1:
        return (Keyword(":" + s), form)
    else:
        raise SyntaxError('EOF while reading keyword')


def _read_symbol(form):
    """Read a symbol."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading symbol')
    if not form[0].isalpha():
        raise SyntaxError('expected alpha char as first char of symbol')
    s = ""
    while len(form) > 0:
        ch = form[0]
        if not (ch.isalpha() or ch.isdigit() or ch == '-' or ch == ":"):
            if s == "t":
                return (True, form)
            elif s == "nil":
                return (False, form)
            else:
                return (Symbol(s), form)
        else:
            s = s + ch
            form = form[1:]

    if len(s) > 0:
        return (Symbol(s), form)
    else:
        raise SyntaxError('EOF while reading symbol')


def _read_int(form):
    """Read an integer."""
    if len(form) == 0:
        raise SyntaxError('unexpected EOF while reading int')
    s = ""
    while (len(form) > 0):
        ch = form[0]
        if not (ch.isdigit() or ch == '-'):
            return (int(s), form)
        else:
            s = s + ch
            form = form[1:]

    if len(s) > 0:
        return (int(s), form)
    else:
        raise SyntaxError('EOF while reading int')


def to_string(exp):
    """Convert a Python object back into a Lisp-readable string."""
    if isinstance(exp, list):
        return '(' + ' '.join(map(to_string, exp)) + ')'
    else:
        return _atom_to_str(exp)


def _atom_to_str(exp):
    if exp and (type(exp) == type(True)):
        return "t"
    elif (not exp) and (type(exp) == type(False)):
        return "nil"
    elif type(exp) == Symbol:
        return exp.val
    elif isinstance(exp, str):
        return "\"" + exp.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
    else:
        return str(exp)