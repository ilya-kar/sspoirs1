import sys

from app.tcp.tcp_client import TCPClient
from app.udp.udp_client import UDPClient


def create_client(protocol, ip, port) -> TCPClient | UDPClient:
    if protocol == "tcp":
        return TCPClient(ip, port)
    else:
        return UDPClient(ip, port)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python client.py {tcp | udp} <ip> <port>")
        sys.exit(1)

    protocol = sys.argv[1]
    ip = sys.argv[2]
    port = int(sys.argv[3])

    try:
        client = create_client(protocol, ip, port)
        client.start()
    except OSError as e:
        print(f"Error: {e}")
