import sys

from app.protocol import PORT
from app.tcp.tcp_server import TCPServer
from app.udp.udp_server import UDPServer


def create_server(protocol: str, ip: str) -> TCPServer | UDPServer:
    if protocol == "tcp":
        return TCPServer(ip, PORT)
    elif protocol == "udp":
        return UDPServer()
    else:
        raise ValueError("protocol must be tcp or udp")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python client.py {tcp | udp} <ip>")
        sys.exit(1)

    protocol = sys.argv[1].lower()
    ip = sys.argv[2]

    try:
        server = create_server(protocol, ip)
        server.start()
    except Exception as e:
        print(f"Error: {e}")
