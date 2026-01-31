import datetime
import os
import socket
import struct
import sys

import app.protocol as proto

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")
os.makedirs(BASE_DIR, exist_ok=True)

PORT = 8080
BACKLOG = 1


class CommandHandler:
    def __init__(self):
        self.simple_commands = {"ECHO": self.echo, "TIME": self.time, "EXIT": self.exit}

    def handle(self, sock: socket.socket, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        result = ""
        if cmd == "DOWNLOAD":
            self.download(sock, arg)
        elif cmd in self.simple_commands:
            result = self.simple_commands[cmd](arg)
        else:
            result = f"Unknown command: {cmd}".encode()

        if isinstance(result, str):
            result = result.encode()

        proto.send_data(sock, result)

    def echo(self, arg: str) -> str:
        return arg

    def time(self, _) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def exit(self, _) -> str:
        return "Bye!"

    def download(self, sock: socket.socket, filename: str):
        safe_name = os.path.normpath(filename).replace("\\", "/")
        file_path = os.path.join(BASE_DIR, safe_name)
        real_path = os.path.realpath(file_path)

        if not real_path.startswith(os.path.realpath(BASE_DIR)):
            proto.send_data(sock, b"ERR")
            proto.send_data(sock, b"Access denied.")
            return

        if not os.path.isfile(real_path):
            proto.send_data(sock, b"ERR")
            proto.send_data(sock, f"File '{filename}' not found.".encode())
            return

        proto.send_data(sock, b"OK")

        file_size = os.path.getsize(real_path)
        proto.send_data(sock, struct.pack("!Q", file_size))

        with open(real_path, "rb") as f:
            while chunk := f.read(4096):
                proto.send_data(sock, chunk)


class Server:
    def start(self, ip: str, port: int):
        sock = self.init_socket(ip, port)
        print(f"Server is listening on {ip}:{port}")

        try:
            while True:
                conn, addr = sock.accept()
                print(f"Client {addr[0]}:{addr[1]} connected")

                try:
                    self.handle_client(conn)
                except (ConnectionError, BrokenPipeError):
                    pass
                finally:
                    conn.close()
                    print(f"Client {addr[0]}:{addr[1]} disconnected")
        finally:
            sock.close()

    def init_socket(self, ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip, port))
        sock.listen(BACKLOG)
        return sock

    def handle_client(self, conn: socket.socket):
        handler = CommandHandler()
        while True:
            message = proto.recv_data(conn).decode()
            handler.handle(conn, message)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python client.py <ip>")
        sys.exit(1)

    server = Server()
    try:
        server.start(sys.argv[1], PORT)
    except KeyboardInterrupt:
        print("\nServer is shutting down...")
    except OSError as e:
        print(f"Error: {e}")
