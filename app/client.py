import os
import socket
import struct
import sys
import time

import app.protocol as proto
from app.protocol import Command


class Client:
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port

    def new_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        proto.enable_keepalive(sock)
        return sock

    def connect(self):
        self.sock = self.new_socket()
        self.sock.connect((self.ip, self.port))

    def start(self):
        while True:
            try:
                self.connect()
                print("Connected to the server")
                self.handle_input()
            except (KeyboardInterrupt, proto.ExitException):
                print("\nExiting...")
                break
            except ConnectionRefusedError:
                print("Server unavailable")
                break
            except (ConnectionError, TimeoutError) as e:
                print("\nConnection with the server was lost")
                print(f"Details: {e}")
                answer = input("Try to reconnect? [y/n]: ").strip().lower()
                if answer != "y":
                    break
                print("Reconnecting...")
            finally:
                self.sock.close()

    def handle_input(self):
        while True:
            message = input("> ")
            if not message:
                continue
            self.handle_command(message)

    def handle_command(self, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cmd = Command(cmd)
        except ValueError:
            cmd = None

        if cmd is Command.UPLOAD:
            self.upload(arg)
            return

        proto.send_data(self.sock, message.encode())

        if cmd is Command.DOWNLOAD:
            self.download(arg)
        else:
            response = proto.recv_data(self.sock).decode()
            print(response)

        if cmd is Command.EXIT:
            raise proto.ExitException

    def download(self, arg: str):
        base_filename = arg.replace("\\", "/").split("/")[-1]
        temp_filename = base_filename + ".part"

        data = proto.recv_data(self.sock)
        status = data[0]
        msg = data[1:]

        if status == proto.STATUS_ERR:
            print(msg.decode())
            return

        client_file_size = 0
        mode = "wb"

        if status == proto.STATUS_APPEND:
            try:
                client_file_size = os.path.getsize(temp_filename)
                mode = "ab"
            except FileNotFoundError:
                pass
            proto.send_data(self.sock, struct.pack("!Q", client_file_size))

        file_size = struct.unpack("!Q", msg)[0]
        print(f"Downloading file '{arg}'...")

        start_time = time.time()
        received = client_file_size
        proto.print_transfer_status(received, file_size)

        with open(temp_filename, mode) as f:
            while received < file_size:
                chunk = proto.recv_data(self.sock)
                f.write(chunk)
                received += len(chunk)
                proto.print_transfer_status(received, file_size)

        os.replace(temp_filename, base_filename)

        print("\nDone")
        proto.print_data_speed(start_time, received - client_file_size)

    def upload(self, arg: str):
        real_path = os.path.realpath(arg)

        if not os.path.isfile(real_path):
            print(f"ERR: File '{arg}' not found")
            return

        proto.send_data(self.sock, f"UPLOAD {arg}".encode())

        file_size = os.path.getsize(real_path)
        proto.send_data(self.sock, struct.pack("!Q", file_size))

        data = proto.recv_data(self.sock)
        status = data[0]
        msg = data[1:]

        seek = 0
        if status == proto.STATUS_APPEND:
            seek = struct.unpack("!Q", msg)[0]

        print(f"Uploading file '{arg}'...")

        start_time = time.time()
        sent = seek
        proto.print_transfer_status(sent, file_size)

        with open(real_path, "rb") as f:
            f.seek(sent)
            while chunk := f.read(4096):
                proto.send_data(self.sock, chunk)
                sent += len(chunk)
                proto.print_transfer_status(sent, file_size)

        print("\nDone")
        proto.print_data_speed(start_time, sent - seek)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python client.py <ip> <port>")
        sys.exit(1)

    try:
        client = Client(sys.argv[1], int(sys.argv[2]))
        print("Connecting...")
        client.start()
    except ValueError:
        print("Port must be a number")
    except OSError as e:
        print(f"Error: {e}")
