"""Single-threaded ENet transport with explicitly configured peer addresses."""
import ipaddress
import time
from dataclasses import dataclass

import enet


@dataclass
class Pending:
    expected: str
    deadline: float
    result: dict | None = None
    error: str | None = None
    started: float | None = None
    received: int = 0
    invalid: int = 0
    unexpected_responses: int = 0


class Transport:
    def __init__(self, codec, port=0, bind='127.0.0.1', allowed=()):
        self.codec = codec
        self.allowed = set(allowed)
        self.host = enet.Host(enet.Address(bind.encode(), port), 32, 2, 0, 0)
        self.peers = {}
        self.pending = {}

    @property
    def port(self):
        return self.host.address.port

    def connect(self, host, port):
        if not ipaddress.ip_address(host).is_loopback and host not in self.allowed:
            raise ValueError('Peer address is not configured')
        return self.host.connect(enet.Address(host.encode('ascii'), port), 2)

    @staticmethod
    def address(peer):
        return (str(peer.address.host), peer.address.port)

    def send(self, peer, clear):
        if not ipaddress.ip_address(peer.address.host).is_loopback and peer.address.host not in self.allowed:
            raise ValueError('Peer address rejected')
        if len(clear) > 60000:
            raise ValueError('Message too large')
        peer.send(0, enet.Packet(self.codec.encrypt(clear), enet.PACKET_FLAG_RELIABLE))
        self.host.flush()

    def request(self, peer, command, fields, response, timeout=3):
        address = self.address(peer)
        if address in self.pending:
            raise ValueError('One outstanding request per peer is supported')
        if timeout <= 0:
            raise ValueError('Invalid timeout')
        now = time.monotonic()
        pending = Pending(response, now+timeout, started=now)
        self.send(peer, self.codec.command(command, fields))
        self.pending[address] = pending
        return pending

    def poll(self, wait_ms=0):
        event = self.host.service(wait_ms)
        output = None
        if event.type == enet.EVENT_TYPE_CONNECT:
            address = self.address(event.peer)
            if not ipaddress.ip_address(address[0]).is_loopback and address[0] not in self.allowed:
                event.peer.disconnect_now()
                return None
            self.peers[address] = event.peer
            output = ('connected', event.peer, None)
        elif event.type == enet.EVENT_TYPE_DISCONNECT:
            address = self.address(event.peer)
            self.peers.pop(address, None)
            pending = self.pending.pop(address, None)
            if pending:
                pending.error = 'disconnected'
            output = ('disconnected', event.peer, None)
        elif event.type == enet.EVENT_TYPE_RECEIVE:
            address = self.address(event.peer)
            pending = self.pending.get(address)
            if pending:
                pending.received += 1
            try:
                if len(event.packet.data) > 60008:
                    raise ValueError('Message too large')
                message = self.codec.decode(self.codec.decrypt(event.packet.data))
            except Exception:
                # Bad legacy input must not crash the service or satisfy a request.
                if pending:
                    pending.invalid += 1
                output = ('invalid', event.peer, None)
            else:
                if pending and time.monotonic() < pending.deadline:
                    body = message.get('[protobuffers.response]', {})
                    if f'[protobuffers.{pending.expected}]' in body:
                        pending.result = body[f'[protobuffers.{pending.expected}]']
                        self.pending.pop(address)
                    elif body:
                        pending.unexpected_responses += 1
                output = ('message', event.peer, message)
        now = time.monotonic()
        for address, pending in list(self.pending.items()):
            if now >= pending.deadline:
                pending.error = 'timeout'
                self.pending.pop(address)
                # No matching request UUID on wire: reset this session so a late
                # response cannot satisfy a later request on the same connection.
                peer = self.peers.pop(address, None)
                if peer:
                    peer.disconnect_now()
        return output

    def close(self):
        for peer in self.peers.values():
            peer.disconnect_now()
        self.peers.clear()
        for pending in self.pending.values():
            pending.error = 'closed'
        self.pending.clear()
        self.host = None
