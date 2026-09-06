import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from fermax.config import EXAMPLE
from fermax.identity import Announcer
from fermax.protocol import Codec


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.now=[0.]
        self.codec=Codec(None,b'01234567ABCDEFGHabcdefgh')
        self.transport=SimpleNamespace(peers={},connect=Mock(return_value=Mock()),send=Mock())
        self.config=copy.deepcopy(EXAMPLE)
        self.notice=Mock()
        self.announcer=Announcer(self.transport,self.codec,self.config,self.notice,lambda:self.now[0])

    def test_startup_and_minute_refresh_only_configured_identity(self):
        self.announcer.tick()
        self.transport.connect.assert_called_once_with('192.0.2.20',56102)
        self.transport.send.assert_not_called()
        self.transport.peers[('192.0.2.20',56102)]=object()
        self.announcer.tick()
        data=self.transport.send.call_args.args[1]
        fields=self.codec.decode(data)['[protobuffers.event]']['[protobuffers.notifyIPProtocolEvent]']
        self.assertEqual(fields,{'ipAdresses':[{'ip_address':'192.0.2.10','protocol':'LYNX','delete':False}],
                                 'block':1,'unit':'0101','gateway':''})
        self.now[0]=59;self.announcer.tick();self.assertEqual(self.transport.send.call_count,1)
        self.now[0]=60;self.announcer.tick();self.assertEqual(self.transport.send.call_count,2)
        self.assertEqual(self.notice.call_count,1)

    def test_unreachable_peer_is_released_and_retried_later(self):
        self.announcer.tick()
        self.now[0]=6;self.announcer.tick()
        self.transport.connect.return_value.disconnect_now.assert_called_once()
        self.assertEqual(self.announcer.waiting,{})
        self.transport.send.assert_not_called()
        self.now[0]=60;self.announcer.tick()
        self.assertEqual(self.transport.connect.call_count,2)
