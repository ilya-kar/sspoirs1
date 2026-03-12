import os
import struct
import threading
import time

import app.protocol as proto
from app.protocol import Command
from app.udp.reliable_udp import ReliableUDP


class UDPClient:
    def __init__(self, ip: str, port: int):
        self.sock = self.new_socket(ip, port)
        self.thread = threading.Thread(target=self.worker)
        self.stop = threading.Event()
        self.check_event_loop = threading.Event()
        self.thread.start()

    def worker(self):
        while not self.stop.is_set():
            try:
                if self.check_event_loop.wait(0.1):
                    self.sock._event_loop_step()
                    time.sleep(0.005)
            except OSError:
                pass

    def new_socket(self, ip: str, port: int):
        sock = ReliableUDP()
        sock._addr = (ip, port)
        sock.set_timeout(30)
        return sock

    def start(self):
        try:
            self.handle_input()
        except (KeyboardInterrupt, proto.ExitException):
            print("\nExiting...")
        finally:
            self.stop.set()
            self.thread.join()
            self.sock.close()

    def handle_input(self):
        while True:
            try:
                self.check_event_loop.set()
                message = input("> ")
                if message:
                    self.check_event_loop.clear()
                    self.handle_command(message)
            except TimeoutError as e:
                print("\nError occurred during send or recv data from the server")
                print(f"Details: {e}")

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
        elif cmd is Command.EXIT:
            raise proto.ExitException

        self.sock.send(message.encode())

        if cmd is Command.DOWNLOAD:
            self.download(arg)
        else:
            response = self.sock.recv().decode()
            print(response)

    def download(self, arg: str):
        base_filename = arg.replace("\\", "/").split("/")[-1]
        temp_filename = base_filename + ".part"

        data = self.sock.recv()
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
            self.sock.send(struct.pack("!Q", client_file_size))

        file_size = struct.unpack("!Q", msg)[0]
        print(f"Downloading file '{arg}'...")

        start_time = time.time()
        received = client_file_size
        proto.print_transfer_status(received, file_size)

        last_update = 0

        with open(temp_filename, mode) as f:
            while received < file_size:
                chunk = self.sock.recv(min(6960, file_size - received))
                f.write(chunk)
                received += len(chunk)

                now = time.time()
                if now - last_update > 1 or received == file_size:
                    proto.print_transfer_status(received, file_size)
                    last_update = now

        os.replace(temp_filename, base_filename)

        print("\nDone")
        proto.print_data_speed(start_time, received - client_file_size)

    def upload(self, arg: str):
        real_path = os.path.realpath(arg)

        if not os.path.isfile(real_path):
            print(f"ERR: File '{arg}' not found")
            return

        self.sock.send(f"UPLOAD {arg}".encode())

        file_size = os.path.getsize(real_path)
        self.sock.send(struct.pack("!Q", file_size))

        data = self.sock.recv()
        status = data[0]
        msg = data[1:]

        seek = 0
        if status == proto.STATUS_APPEND:
            seek = struct.unpack("!Q", msg)[0]

        print(f"Uploading file '{arg}'...")

        start_time = time.time()
        sent = seek
        proto.print_transfer_status(sent, file_size)

        last_update = 0

        with open(real_path, "rb") as f:
            f.seek(sent)
            while chunk := f.read(6960):
                self.sock.send(chunk)
                sent += len(chunk)

                now = time.time()
                if now - last_update > 1 or sent == file_size:
                    proto.print_transfer_status(sent, file_size)
                    last_update = now

        print("\nDone")
        proto.print_data_speed(start_time, sent - seek)
