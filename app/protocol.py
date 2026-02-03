import enum
import socket
import struct

STATUS_OK = 0
STATUS_ERR = 1


class Command(str, enum.Enum):
    ECHO = "ECHO"
    TIME = "TIME"
    EXIT = "EXIT"
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"


class ExitException(Exception):
    pass


class PeerDisconnected(Exception):
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


def print_data_speed(start_time: float, bytes: int, label: str = "Average speed"):
    import time

    elapsed = time.time() - start_time
    speed_MB_s = (bytes / (1024**2)) / elapsed
    print(f"{label}: {speed_MB_s:.2f} MB/s")
