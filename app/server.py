import datetime
import os
import socket
import struct
import sys

import app.protocol as proto
from app.protocol import Command

BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "server_files"
)
os.makedirs(BASE_DIR, exist_ok=True)

PORT = 8080
BACKLOG = 1


class Server:
    def start(self, ip: str, port: int):
        sock = self.init_socket(ip, port)
        print(f"Server is listening on {ip}:{port}")

        try:
            while True:
                conn, addr = sock.accept()
                ip, port = addr
                print(f"Client {ip}:{port} connected")

                try:
                    self.handle_client(conn)
                except (ConnectionError, BrokenPipeError):
                    pass
                finally:
                    conn.close()
                    print(f"Client {ip}:{port} disconnected")
        finally:
            sock.close()

    def init_socket(self, ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip, port))
        sock.listen(BACKLOG)
        return sock

    def handle_client(self, conn: socket.socket):
        while True:
            message = proto.recv_data(conn).decode()
            self.handle_command(conn, message)

    def handle_command(self, conn: socket.socket, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cmd = Command(cmd)
        except ValueError:
            proto.send_data(conn, f"ERR: Unknown command: {cmd}".encode())

        if cmd is Command.ECHO:
            proto.send_data(conn, arg.encode())
        elif cmd is Command.TIME:
            time = datetime.datetime.now().strftime("%H:%M:%S")
            proto.send_data(conn, time.encode())
        elif cmd is Command.EXIT:
            proto.send_data(conn, b"Bye!")
        elif cmd is Command.DOWNLOAD:
            self.download(conn, arg)

    def download(self, sock: socket.socket, filename: str):
        safe_name = os.path.normpath(filename).replace("\\", "/")
        file_path = os.path.join(BASE_DIR, safe_name)
        real_path = os.path.realpath(file_path)

        if not real_path.startswith(os.path.realpath(BASE_DIR)):
            msg = bytes([proto.STATUS_ERR]) + b"ERR: Access denied"
            proto.send_data(sock, msg)
            return

        if not os.path.isfile(real_path):
            msg = (
                bytes([proto.STATUS_ERR]) + f"ERR: File '{filename}' not found".encode()
            )
            proto.send_data(sock, msg)
            return

        file_size = os.path.getsize(real_path)
        msg = bytes([proto.STATUS_OK]) + struct.pack("!Q", file_size)
        proto.send_data(sock, msg)

        with open(real_path, "rb") as f:
            while chunk := f.read(4096):
                proto.send_data(sock, chunk)


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
