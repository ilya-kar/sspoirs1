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


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError()
        data += chunk
    return data


def recv_data(sock: socket.socket) -> bytes:
    raw_len = recv_exact(sock, 4)
    length = struct.unpack("!I", raw_len)[0]
    return recv_exact(sock, length)


def send_data(sock: socket.socket, data: bytes):
    sock.sendall(struct.pack("!I", len(data)))
    sock.sendall(data)
