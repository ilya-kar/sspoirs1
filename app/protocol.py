import socket
import struct


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
