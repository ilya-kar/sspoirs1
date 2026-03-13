import datetime
import os
import secrets
import select
import socket
import struct
from typing import Generator, Optional

import app.protocol as proto
from app.protocol import BACKLOG, CHUNK, FORMAT_HEADER, HEADER, Command


class Client:
    def __init__(self, addr: tuple[str, int]):
        self.addr = addr
        self.conn_id = ""
        self.is_conn_id_set = False
        self.task: Optional[Generator[str, None, None]] = None
        self.send_buffer = b""
        self.recv_buffer = bytearray()
        self.msg_length = None
        self.ready_to_read = False
        self.waiting_for: str | None = None


class Session:
    def __init__(self):
        self.cmd = Command.DOWNLOAD
        self.filename = ""


class TCPServer:
    def __init__(self, ip: str, port: int, base_dir: str):
        self.server_sock = self.new_socket(ip, port)
        self.base_dir = base_dir
        self.sessions: dict[str, Session] = {}
        self.clients: dict[socket.socket, Client] = {}
        print(f"Server is listening on {ip}:{port}")

    def new_socket(self, ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip, port))
        sock.listen(BACKLOG)
        sock.setblocking(False)
        return sock

    def start(self):
        try:
            while True:
                rlist = [self.server_sock] + list(self.clients.keys())
                wlist = [
                    sock for sock, client in self.clients.items() if client.send_buffer
                ]

                readable, writable, _ = select.select(rlist, wlist, [], 0.1)
                self.handle_readable(readable)
                self.handle_writable(writable)
                self.handle_tasks()
        except KeyboardInterrupt:
            print("\nServer is shutting down...")
        finally:
            self.server_sock.close()

    def handle_readable(self, readable: list[socket.socket]):
        for sock in readable:
            if sock is self.server_sock:
                client, addr = self.server_sock.accept()
                client.setblocking(False)
                proto.enable_keepalive(client)
                self.clients[client] = Client(addr)
                print(f"Client {addr} connected")
            else:
                try:
                    client = self.clients[sock]
                    self.try_to_read(sock, client)
                    if client.task is None and client.ready_to_read:
                        self.handle_message(client)
                except (ConnectionError, proto.ExitException):
                    print(f"Client {sock.getpeername()} disconnected")
                    sock.close()
                    del self.clients[sock]

    def handle_writable(self, writable: list[socket.socket]):
        for sock in writable:
            client = self.clients[sock]
            try:
                client.send_buffer = proto.send_some(sock, client.send_buffer)
            except ConnectionError:
                print(f"Client {sock.getpeername()} disconnected")
                sock.close()
                del self.clients[sock]

    def handle_tasks(self):
        for client in self.clients.values():
            if not client.task:
                continue

            if client.waiting_for == "read" and not client.ready_to_read:
                continue

            if client.waiting_for == "write" and client.send_buffer:
                continue

            try:
                event = next(client.task)
                client.waiting_for = event
            except StopIteration:
                client.task = None
                client.waiting_for = None

    def try_to_read(self, sock: socket.socket, client: Client):
        try:
            if client.msg_length is None:
                client.recv_buffer.extend(
                    proto.recv_some(sock, HEADER - len(client.recv_buffer))
                )
                if len(client.recv_buffer) == HEADER:
                    client.msg_length = struct.unpack(
                        FORMAT_HEADER, client.recv_buffer
                    )[0]
                    client.recv_buffer = bytearray()
            else:
                client.recv_buffer.extend(
                    proto.recv_some(sock, client.msg_length - len(client.recv_buffer))
                )
                if len(client.recv_buffer) == client.msg_length:
                    client.ready_to_read = True
        except BlockingIOError:
            pass

    def clear_recv_buffer(self, client: Client):
        client.recv_buffer = bytearray()
        client.msg_length = None
        client.ready_to_read = False

    def handle_message(self, client: Client):
        if client.is_conn_id_set:
            now = datetime.datetime.now().strftime("%H:%M:%S")
            message = client.recv_buffer.decode()
            print(f"[{now}] Received message from the client {client.addr}: {message}")
            self.handle_command(client, message)
        else:
            self.handle_service_packet(client, client.recv_buffer)
        self.clear_recv_buffer(client)

    def handle_command(self, client: Client, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cmd = Command(cmd)
        except ValueError:
            msg = f"ERR: Unknown command: {parts[0]}".encode()
            client.send_buffer = proto.create_data(msg)
            return

        if cmd is Command.ECHO:
            client.send_buffer = proto.create_data(arg.encode())
        elif cmd is Command.TIME:
            time = datetime.datetime.now().strftime("%H:%M:%S")
            client.send_buffer = proto.create_data(time.encode())
        elif cmd is Command.EXIT:
            raise proto.ExitException
        elif cmd is Command.DOWNLOAD:
            client.task = self.download(client, arg)
        elif cmd is Command.UPLOAD:
            client.task = self.upload(client, arg)

    def handle_service_packet(self, client: Client, message: bytes):
        if message[0] == proto.STATUS_CONN_NEED_ID:
            conn_id = self.create_session()
            message = bytes([proto.STATUS_CONN_ID]) + conn_id.encode()
        elif message[0] == proto.STATUS_CONN_ID:
            conn_id = message[1:].decode()
            message = bytes([proto.STATUS_OK])
            if conn_id not in self.sessions:
                conn_id = self.create_session()
                message = bytes([proto.STATUS_CONN_ID]) + conn_id.encode()
        else:
            raise ConnectionError("Invalid service packet")
        client.conn_id = conn_id
        client.is_conn_id_set = True
        client.send_buffer = proto.create_data(message)

    def create_session(self) -> str:
        conn_id = secrets.token_hex(8)
        self.sessions[conn_id] = Session()
        return conn_id

    def download(self, client: Client, arg: str):
        file_path = os.path.join(self.base_dir, arg)
        real_path = os.path.realpath(file_path)

        if not real_path.startswith(os.path.realpath(self.base_dir)):
            msg = bytes([proto.STATUS_ERR]) + b"ERR: Access denied"
            client.send_buffer = proto.create_data(msg)
            return

        if not os.path.isfile(real_path):
            msg = bytes([proto.STATUS_ERR]) + f"ERR: File '{arg}' not found".encode()
            client.send_buffer = proto.create_data(msg)
            return

        seek = 0
        file_size = os.path.getsize(real_path)
        msg = bytearray([proto.STATUS_OK]) + struct.pack("!Q", file_size)

        session = self.sessions[client.conn_id]
        if session.cmd == Command.DOWNLOAD and session.filename == real_path:
            msg[0] = proto.STATUS_APPEND

        client.send_buffer = proto.create_data(msg)
        yield "write"

        if msg[0] == proto.STATUS_APPEND:
            yield "read"
            seek = struct.unpack("!Q", client.recv_buffer)[0]
            self.clear_recv_buffer(client)

        session.cmd = Command.DOWNLOAD
        session.filename = real_path

        with open(real_path, "rb") as f:
            f.seek(seek)
            while chunk := f.read(CHUNK):
                client.send_buffer = proto.create_data(chunk)
                yield "write"

    def upload(self, client: Client, arg: str):
        conn_id = client.conn_id
        session = self.sessions[conn_id]

        base_filename = arg.replace("\\", "/").split("/")[-1]
        temp_filename = base_filename + f"{conn_id}.part"
        file_path = os.path.join(self.base_dir, temp_filename)

        yield "read"
        file_size = struct.unpack("!Q", client.recv_buffer)[0]
        self.clear_recv_buffer(client)

        mode = "wb"
        server_file_size = 0
        msg = bytearray([proto.STATUS_OK])

        if session.cmd == Command.UPLOAD and session.filename == base_filename:
            try:
                server_file_size = os.path.getsize(file_path)
                mode = "ab"
                msg[0] = proto.STATUS_APPEND
                msg[1:] = struct.pack("!Q", server_file_size)
            except FileNotFoundError:
                pass

        client.send_buffer = proto.create_data(msg)
        yield "write"

        received = server_file_size
        session.cmd = Command.UPLOAD
        session.filename = base_filename

        with open(file_path, mode) as f:
            while received < file_size:
                yield "read"
                chunk = client.recv_buffer
                f.write(chunk)
                received += len(chunk)
                self.clear_recv_buffer(client)

        final_path = file_path.removesuffix(f"{conn_id}.part")
        os.replace(file_path, final_path)
