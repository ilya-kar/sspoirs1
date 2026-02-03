import datetime
import os
import socket
import struct
import sys
import time

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
        server_sock = self.init_socket(ip, port)
        print(f"Server is listening on {ip}:{port}")

        try:
            while True:
                self.client_sock, addr = server_sock.accept()
                ip, port = addr
                print(f"Client {ip}:{port} connected")

                try:
                    self.handle_client()
                except proto.ExitException:
                    print(f"Client {ip}:{port} disconnected")
                except (proto.PeerDisconnected, BrokenPipeError) as e:
                    print(f"Connection with the client {ip}:{port} was lost")
                    print(f"Details: {e}")
                finally:
                    self.client_sock.close()
        except KeyboardInterrupt:
            print("\nServer is shutting down...")
        finally:
            server_sock.close()

    def init_socket(self, ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip, port))
        sock.listen(BACKLOG)
        return sock

    def handle_client(self):
        while True:
            message = proto.recv_data(self.client_sock).decode()
            time = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{time}] Received message: {message}")
            self.handle_command(message)

    def handle_command(self, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cmd = Command(cmd)
        except ValueError:
            proto.send_data(
                self.client_sock, f"ERR: Unknown command: {parts[0]}".encode()
            )

        if cmd is Command.ECHO:
            proto.send_data(self.client_sock, arg.encode())
        elif cmd is Command.TIME:
            time = datetime.datetime.now().strftime("%H:%M:%S")
            proto.send_data(self.client_sock, time.encode())
        elif cmd is Command.EXIT:
            proto.send_data(self.client_sock, b"Bye!")
            raise proto.ExitException
        elif cmd is Command.DOWNLOAD:
            self.download(arg)
        elif cmd is Command.UPLOAD:
            self.upload(arg)

    def download(self, arg: str):
        file_path = os.path.join(BASE_DIR, arg)
        real_path = os.path.realpath(file_path)

        if not real_path.startswith(os.path.realpath(BASE_DIR)):
            msg = bytes([proto.STATUS_ERR]) + b"ERR: Access denied"
            proto.send_data(self.client_sock, msg)
            return

        if not os.path.isfile(real_path):
            msg = bytes([proto.STATUS_ERR]) + f"ERR: File '{arg}' not found".encode()
            proto.send_data(self.client_sock, msg)
            return

        file_size = os.path.getsize(real_path)
        msg = bytes([proto.STATUS_OK]) + struct.pack("!Q", file_size)
        proto.send_data(self.client_sock, msg)

        print(f"Uploading file '{arg}'...")

        start_time = time.time()
        sent = 0
        next_percent = 1

        with open(real_path, "rb") as f:
            while chunk := f.read(4096):
                proto.send_data(self.client_sock, chunk)
                sent += len(chunk)
                next_percent = proto.print_transfer_status(
                    sent, file_size, next_percent
                )

        print("\nDone")
        proto.print_data_speed(start_time, sent, "Upload speed")

    def upload(self, arg: str):
        filename = arg.replace("\\", "/").split("/")[-1]
        file_path = os.path.join(BASE_DIR, filename)

        raw_file_size = proto.recv_data(self.client_sock)
        file_size = struct.unpack("!Q", raw_file_size)[0]

        print(f"Downloading file '{filename}'...")

        start_time = time.time()
        received = 0
        next_percent = 1

        with open(file_path, "wb") as f:
            while received < file_size:
                chunk = proto.recv_data(self.client_sock)
                f.write(chunk)
                received += len(chunk)
                next_percent = proto.print_transfer_status(
                    received, file_size, next_percent
                )

        print("\nDone")
        proto.print_data_speed(start_time, received, "Download speed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python client.py <ip>")
        sys.exit(1)

    server = Server()
    try:
        server.start(sys.argv[1], PORT)
    except OSError as e:
        print(f"Error: {e}")
