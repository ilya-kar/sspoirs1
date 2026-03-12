import os
import sys

from app.protocol import PORT
from app.tcp.tcp_server import TCPServer
from app.udp.udp_server import UDPServer


def create_server(protocol, ip, base_dir) -> TCPServer | UDPServer:
    if protocol == "tcp":
        return TCPServer(ip, PORT, base_dir)
    else:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python client.py {tcp | udp} <ip>")
        sys.exit(1)

    protocol = sys.argv[1]
    ip = sys.argv[2]

    base_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "server_files"
    )
    os.makedirs(base_dir, exist_ok=True)

    server = create_server(protocol, ip, base_dir)

    try:
        server.start()
    except OSError as e:
        print(f"Error: {e}")
