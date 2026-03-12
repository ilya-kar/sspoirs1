import errno
import math
import socket
import struct
import time

import app.protocol as proto

MAX_WINDOW_SIZE = 5
RTO = 20
DELAY_ACK = RTO / 3

DGRAM_SIZE = 1400
HEADER_SIZE = 8
PAYLOAD_SIZE = DGRAM_SIZE - HEADER_SIZE


class Datagram:
    def __init__(self, payload: bytes, send_time: float):
        self.payload = payload
        self.send_time = send_time
        self.in_flight = False


class ReliableUDP:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self._timeout = None
        self._tda = 0
        self._need_to_ack = False
        self._sn = 0
        self._an = 0
        self._send_buffer: dict[int, Datagram] = {}
        self._recv_buffer: dict[int, bytes] = {}
        self._addr: tuple[str, int] = ("0.0.0.0", 0)
        self._window_size = MAX_WINDOW_SIZE

    def bind(self, addr: tuple[str, int]):
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(addr)

    def set_timeout(self, seconds: float | None):
        self._timeout = seconds

    def sendto(self, msg: bytes, addr: tuple[str, int]):
        if addr != self._addr:
            self._addr = addr
            self.reset()

        n = math.ceil(len(msg) / PAYLOAD_SIZE)

        temp_sn = self._sn
        for i in range(n):
            payload = msg[i * PAYLOAD_SIZE : (i + 1) * PAYLOAD_SIZE]
            dgram = Datagram(payload, 0)
            self._send_buffer[temp_sn] = dgram
            temp_sn += 1

        start_time = time.monotonic()
        while self._sn < temp_sn:
            try:
                self._event_loop_step()
            except OSError as e:
                if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
                    pass
                else:
                    raise
            if (
                self._timeout is not None
                and time.monotonic() - start_time > self._timeout
            ):
                raise socket.timeout("timeout")
            time.sleep(0.005)

    def send(self, msg: bytes):
        self.sendto(msg, self._addr)

    def recvfrom(self, size: int = PAYLOAD_SIZE) -> tuple[bytes, tuple[str, int]]:
        n = math.ceil(size / PAYLOAD_SIZE)
        except_an = self._an + n

        for an in self._recv_buffer:
            if an < self._an:
                except_an -= 1

        start_time = time.monotonic()
        while self._an < except_an:
            try:
                self._event_loop_step()
            except OSError as e:
                if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
                    pass
                else:
                    raise
            if (
                self._timeout is not None
                and time.monotonic() - start_time > self._timeout
            ):
                raise socket.timeout("timeout")
            time.sleep(0.005)

        msg = bytes()
        for i in range(n, 0, -1):
            msg += self._recv_buffer.pop(self._an - i)

        return (msg, self._addr)

    def recv(self, size: int = PAYLOAD_SIZE) -> bytes:
        msg, _ = self.recvfrom(size)
        return msg

    def _event_loop_step(self):
        try:
            dgram, addr = self.sock.recvfrom(DGRAM_SIZE)
            if addr != self._addr:
                self._addr = addr
                self.reset()
                raise proto.PeerChangedException
            self._handle_dgram(dgram)
        except BlockingIOError:
            pass
        cur_time = time.monotonic() * 1000

        for sn in list(self._send_buffer):
            dgram = self._send_buffer[sn]

            if self._window_size > 0:
                dgram.in_flight = True
                self._window_size -= 1

            if dgram.in_flight and cur_time - dgram.send_time > RTO:
                header = struct.pack("!II", sn, self._an)
                self.sock.sendto(header + dgram.payload, self._addr)
                dgram.send_time = cur_time
                if self._need_to_ack:
                    self._need_to_ack = False

        if self._need_to_ack and cur_time - self._tda > DELAY_ACK:
            header = struct.pack("!II", self._sn, self._an)
            self.sock.sendto(header, self._addr)
            self._need_to_ack = False

    def _handle_dgram(self, dgram: bytes):
        header, payload = dgram[:HEADER_SIZE], dgram[HEADER_SIZE:]
        sn, an = struct.unpack("!II", header)

        if payload and sn <= self._an:
            if not self._need_to_ack:
                self._need_to_ack = True
                self._tda = time.monotonic() * 1000
            if sn == self._an:
                self._recv_buffer[sn] = payload
                self._an += 1

        if len(self._send_buffer) != 0:
            for i in range(self._sn, an):
                self._send_buffer.pop(i)
            self._window_size = self._window_size + an - self._sn
            self._sn = an

    def reset(self):
        self._sn = 0
        self._an = 0
        self._need_to_ack = False
        self._send_buffer.clear()
        self._recv_buffer.clear()
        self._window_size = MAX_WINDOW_SIZE

    def close(self):
        self.sock.close()
