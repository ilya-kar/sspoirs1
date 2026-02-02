import os
import socket
import struct
import sys

import app.protocol as proto
from app.protocol import Command

BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "client_files"
)
os.makedirs(BASE_DIR, exist_ok=True)


class ExitException(Exception):
    pass


class Client:
    def start(self, ip: str, port: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((ip, port))
        self.handle_input(sock)

    def handle_input(self, sock: socket.socket):
        try:
            while True:
                message = input("> ")
                if not message:
                    continue
                self.handle_command(sock, message)
        except (ConnectionError, BrokenPipeError) as e:
            print(f"Error: {e}")
        except ExitException:
            pass
        finally:
            sock.close()

    def handle_command(self, sock: socket.socket, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        try:
            cmd = Command(cmd)
        except ValueError:
            print(f"ERR: Unknown command: {cmd}")
            return

        if cmd is Command.UPLOAD:
            self.upload(sock, arg)
            return

        proto.send_data(sock, message.encode())

        if cmd is Command.DOWNLOAD:
            self.download(sock, arg)
        else:
            response = proto.recv_data(sock).decode()
            print(response)

        if cmd is Command.EXIT:
            raise ExitException

    def download(self, sock: socket.socket, arg: str):
        filename = arg.replace("\\", "/").split("/")[-1]
        file_path = os.path.join(BASE_DIR, filename)

        data = proto.recv_data(sock)
        status = data[0]
        msg = data[1:]

        if status == proto.STATUS_ERR:
            print(msg.decode())
            return

        if status == proto.STATUS_OK:
            file_size = struct.unpack("!Q", msg)[0]

            print("Downloading...")

            with open(file_path, "wb") as f:
                received = 0
                while received < file_size:
                    chunk = proto.recv_data(sock)
                    f.write(chunk)
                    received += len(chunk)

            print("Done")

    def upload(self, sock: socket.socket, arg: str):
        real_path = os.path.realpath(arg)

        if not os.path.isfile(real_path):
            print(f"ERR: File '{arg}' not found")
            return

        proto.send_data(sock, f"UPLOAD {arg}".encode())

        file_size = os.path.getsize(real_path)
        proto.send_data(sock, struct.pack("!Q", file_size))

        print("Uploading...")

        with open(real_path, "rb") as f:
            while chunk := f.read(4096):
                proto.send_data(sock, chunk)

        print("Done")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python client.py <ip> <port>")
        sys.exit(1)

    client = Client()
    try:
        client.start(sys.argv[1], int(sys.argv[2]))
    except KeyboardInterrupt:
        print("\nExit...")
    except ValueError:
        print("Port must be a number")
    except OSError as e:
        print(f"Error: {e}")
