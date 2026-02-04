import ctypes
import enum
import socket
import struct
import sys

STATUS_OK = 0
STATUS_ERR = 1
STATUS_APPEND = 2


class Command(str, enum.Enum):
    ECHO = "ECHO"
    TIME = "TIME"
    EXIT = "EXIT"
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"


class ExitException(Exception):
    pass


class PeerDisconnected(ConnectionError):
    pass


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise PeerDisconnected("Peer closed connection during receiving data")
        data += chunk
    return data


def recv_data(sock: socket.socket) -> bytes:
    raw_len = recv_exact(sock, 4)
    length = struct.unpack("!I", raw_len)[0]
    return recv_exact(sock, length)


def send_data(sock: socket.socket, data: bytes):
    sock.sendall(struct.pack("!I", len(data)))
    sock.sendall(data)


def print_transfer_status(current: int, total: int, next_percent: int) -> int:
    percent = int(current / total * 100)
    if percent >= next_percent:
        print(f"\rStatus: {percent}% ({current}/{total} bytes)", end="")
        return percent + 1
    return next_percent


def format_speed(bytes_transferred: int, elapsed: float) -> str:  # pyright: ignore[reportReturnType]
    if elapsed == 0:
        return "∞ B/s"

    speed = bytes_transferred / elapsed
    units = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
    for unit in units:
        if speed < 1024 or unit == units[-1]:
            return f"{speed:.2f} {unit}"
        speed /= 1024


def print_data_speed(start_time: float, bytes: int, label: str = "Average speed"):
    import time

    elapsed = time.time() - start_time
    print(f"{label}: {format_speed(bytes, elapsed)}")


def enable_keepalive(
    sock: socket.socket, idle: int = 10, interval: int = 5, max_fails: int = 4
):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    if sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)
    elif sys.platform == "win32":
        SIO_KEEPALIVE_VALS = 0x98000004
        keepalive_vals = struct.pack(
            "III",
            idle * 1000,
            interval * 1000,
            max_fails,
        )

        ctypes.windll.ws2_32.WSAIoctl(
            sock.fileno(),
            SIO_KEEPALIVE_VALS,
            keepalive_vals,
            len(keepalive_vals),
            None,
            0,
            ctypes.byref(ctypes.c_ulong()),
            None,
            None,
        )
    else:
        print("Keepalive: not supported on this platform")
