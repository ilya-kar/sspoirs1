import socket
import struct
import sys

import app.protocol as proto


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
                proto.send_data(sock, message.encode())
                self.handle_cmd(sock, message)
                if message.strip().upper() == "EXIT":
                    break
        except (ConnectionError, BrokenPipeError) as e:
            print(f"Error: {e}")
        finally:
            sock.close()

    def handle_cmd(self, sock: socket.socket, message: str):
        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "DOWNLOAD":
            self.download(sock, arg.replace("\\", "/").split("/")[-1])
        else:
            response = proto.recv_data(sock).decode()
            print(response)

    def download(self, sock: socket.socket, filename: str):
        status = proto.recv_data(sock)

        if status == b"ERR":
            msg = proto.recv_data(sock).decode()
            print("Error:", msg)
            return

        if status == b"OK":
            size_bytes = proto.recv_data(sock)
            file_size = struct.unpack("!Q", size_bytes)[0]

            print("Downloading...")

            with open(filename, "wb") as f:
                received = 0
                while received < file_size:
                    chunk = proto.recv_data(sock)
                    f.write(chunk)
                    received += len(chunk)

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
