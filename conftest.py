"""The test suite's guard, loaded for every test directory before collection.

No test may call GitHub (`gh`), open a network connection, or make git talk to
a remote that is not a local path: the real `origin` is a public repository
whose data branch the site serves. Tests use temporary repositories as remotes
and stub `cli.gh` and HTTP calls. A test that trips the guard fails with a
GuardError saying what to stub; git refuses with "transport 'https' not allowed".
"""

import ipaddress
import os
import socket
import subprocess
from pathlib import Path

BLOCKED_PROGRAMS = {"gh", "curl", "wget"}
GIT_LOCAL_ONLY = {"GIT_ALLOW_PROTOCOL": "file"}  # git refuses https, ssh and git transports


class GuardError(RuntimeError):
    pass


def _program(args):
    if isinstance(args, (str, bytes, os.PathLike)):
        words = os.fsdecode(args).split()
        return Path(words[0]).name if words else ""
    return Path(os.fsdecode(args[0])).name if args else ""


class GuardedPopen(subprocess.Popen):
    """Every subprocess call in the suite goes through Popen, including `run` saved at import time."""

    def __init__(self, args, *rest, **kwargs):
        if _program(args) in BLOCKED_PROGRAMS:
            raise GuardError(f"tests must not run {_program(args)} ({args!r}); stub the call instead")
        if kwargs.get("env") is not None:
            kwargs["env"] = {**kwargs["env"], **GIT_LOCAL_ONLY}
        super().__init__(args, *rest, **kwargs)


def _local_host(host):
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host if isinstance(host, str) else host.decode()).is_loopback
    except ValueError:
        return False


def _local_address(address):
    return not isinstance(address, tuple) or _local_host(address[0])  # a non-tuple is a Unix socket path


def _refuse(what):
    raise GuardError(f"tests must not use the network ({what}); stub the request instead")


_saved = {}


def _install():
    _saved.update(
        popen=subprocess.Popen,
        getaddrinfo=socket.getaddrinfo,
        connect=socket.socket.connect,
        connect_ex=socket.socket.connect_ex,
        sendto=socket.socket.sendto,
        env={key: os.environ.get(key) for key in GIT_LOCAL_ONLY},
    )

    def getaddrinfo(host, *args, **kwargs):
        if not _local_host(host):
            _refuse(f"resolve {host}")
        return _saved["getaddrinfo"](host, *args, **kwargs)

    def connect(self, address):
        if not _local_address(address):
            _refuse(f"connect to {address}")
        return _saved["connect"](self, address)

    def connect_ex(self, address):
        if not _local_address(address):
            _refuse(f"connect to {address}")
        return _saved["connect_ex"](self, address)

    def sendto(self, data, *args):
        if not _local_address(args[-1]):
            _refuse(f"send to {args[-1]}")
        return _saved["sendto"](self, data, *args)

    subprocess.Popen = GuardedPopen
    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    os.environ.update(GIT_LOCAL_ONLY)


def _uninstall():
    subprocess.Popen = _saved["popen"]
    socket.getaddrinfo = _saved["getaddrinfo"]
    socket.socket.connect = _saved["connect"]
    socket.socket.connect_ex = _saved["connect_ex"]
    socket.socket.sendto = _saved["sendto"]
    for key, value in _saved["env"].items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def pytest_configure(config):
    _install()


def pytest_unconfigure(config):
    _uninstall()
