import datetime
import os
import struct
import time

import app.protocol as proto
from app.protocol import Command
from app.udp.reliable_udp import ReliableUDP


class UDPServer:
    def __init__(self, ip: str, port: int, base_dir: str):
        self.server_sock = self.new_socket(ip, port)
        self.base_dir = base_dir
        self.session = {"cmd": Command.DOWNLOAD, "filename": "", "client_ip": ""}
        print(f"Server is listening on {ip}:{port}")

    def new_socket(self, ip: str, port: int) -> ReliableUDP:
        sock = ReliableUDP()
        sock.bind((ip, port))
        return sock

    def start(self):
        try:
            while True:
                msg, addr = self.server_sock.recvfrom()
                ip, port = addr
                msg = msg.decode()

                if ip != self.session["client_ip"]:
                    if os.path.exists(self.session["filename"] + ".part"):
                        os.remove(self.session["filename"] + ".part")
                    self.session["filename"] = ""
                    self.session["client_ip"] = ip

                time = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{time}] Received message from the client {ip}:{port}: {msg}")

                try:
                    self.server_sock.set_timeout(30)
                    self.handle_command(msg)
                    self.server_sock.set_timeout(None)
                except TimeoutError as e:
                    print(
                        f"\nError during send or recv data from the client {ip}:{port}"
                    )
                    print(f"Details: {e}")
        except KeyboardInterrupt:
            print("\nServer is shutting down...")
        finally:
            self.server_sock.close()

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
            return

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
        file_path = os.path.join(self.base_dir, arg)
        real_path = os.path.realpath(file_path)

        if not real_path.startswith(os.path.realpath(self.base_dir)):
            msg = bytes([proto.STATUS_ERR]) + b"ERR: Access denied"
            proto.send_data(self.client_sock, msg)
            return

        if not os.path.isfile(real_path):
            msg = bytes([proto.STATUS_ERR]) + f"ERR: File '{arg}' not found".encode()
            proto.send_data(self.client_sock, msg)
            return

        seek = 0
        file_size = os.path.getsize(real_path)
        msg = bytearray([proto.STATUS_OK]) + struct.pack("!Q", file_size)

        if (
            self.session["cmd"] == Command.DOWNLOAD
            and self.session["filename"] == real_path
        ):
            msg[0] = proto.STATUS_APPEND
            proto.send_data(self.client_sock, msg)
            client_raw_file_size = proto.recv_data(self.client_sock)
            seek = struct.unpack("!Q", client_raw_file_size)[0]
        else:
            proto.send_data(self.client_sock, msg)

        print(f"Sending file '{arg}'...")

        start_time = time.time()
        sent = seek
        proto.print_transfer_status(sent, file_size)

        self.session["cmd"] = Command.DOWNLOAD
        self.session["filename"] = real_path

        last_update = 0

        with open(real_path, "rb") as f:
            f.seek(seek)
            while chunk := f.read(4096):
                proto.send_data(self.client_sock, chunk)
                sent += len(chunk)

                now = time.time()
                if now - last_update > 1 or sent == file_size:
                    proto.print_transfer_status(sent, file_size)
                    last_update = now

        print("\nDone")
        proto.print_data_speed(start_time, sent - seek)

    def upload(self, arg: str):
        base_filename = arg.replace("\\", "/").split("/")[-1]
        temp_filename = base_filename + ".part"
        file_path = os.path.join(self.base_dir, temp_filename)

        raw_file_size = proto.recv_data(self.client_sock)
        file_size = struct.unpack("!Q", raw_file_size)[0]

        mode = "wb"
        server_file_size = 0
        msg = bytearray([proto.STATUS_OK])

        if (
            self.session["cmd"] == Command.UPLOAD
            and self.session["filename"] == base_filename
        ):
            try:
                server_file_size = os.path.getsize(file_path)
                mode = "ab"
                msg[0] = proto.STATUS_APPEND
                msg[1:] = struct.pack("!Q", server_file_size)
            except FileNotFoundError:
                pass
            proto.send_data(self.client_sock, msg)
        else:
            proto.send_data(self.client_sock, msg)

        print(f"Receiving file '{base_filename}'...")

        start_time = time.time()
        received = server_file_size
        proto.print_transfer_status(received, file_size)

        self.session["cmd"] = Command.UPLOAD
        self.session["filename"] = base_filename

        last_update = 0

        with open(file_path, mode) as f:
            while received < file_size:
                chunk = proto.recv_data(self.client_sock)
                f.write(chunk)
                received += len(chunk)

                now = time.time()
                if now - last_update > 1 or received == file_size:
                    proto.print_transfer_status(received, file_size)
                    last_update = now

        final_path = file_path.removesuffix(".part")
        os.replace(file_path, final_path)

        print("\nDone")
        proto.print_data_speed(start_time, received - server_file_size)
