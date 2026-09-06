import json
import os
import unittest
from pathlib import Path
from fermax.protocol import SIP
from fermax.sip_live import Signaling, wire


class SIPLiveTests(unittest.TestCase):
    def setUp(self):
        self.out, self.events = [], []
        self.now = [0.]
        self.sip = Signaling('192.0.2.10', ['192.0.2.20'], lambda data,remote:self.out.append((data,remote)),
                             lambda kind,value:self.events.append((kind,value)), lambda:self.now[0])
        self.invite = wire('INVITE sip:192.0.2.10 SIP/2.0',{
            'Via':'SIP/2.0/UDP 192.0.2.20:5060;branch=z9hG4bKexample',
            'To':'<sip:192.0.2.10>','From':'<sip:192.0.2.20>;tag=panel',
            'Call-ID':'example-call','CSeq':'1 INVITE','Content-Type':'application/sdp'},
            'v=0\r\nm=audio 0 RTP/AVP 0\r\nm=video 5010 RTP/AVP 98\r\n')

    def test_incoming_video_and_duplicate_invite(self):
        self.sip.receive(self.invite,'192.0.2.20')
        responses = [SIP.parse(data) for data,_ in self.out]
        self.assertEqual([s.first for s in responses], ['SIP/2.0 100 Trying','SIP/2.0 180 Ringing','SIP/2.0 200 OK'])
        self.assertEqual(responses[-1].audio_port, 0)
        self.sip.receive(self.invite,'192.0.2.20')
        self.assertEqual(self.out[-1],self.out[-2])
        self.assertEqual(sum(k=='incoming' for k,v in self.events),1)

    def test_missing_ack_ends_session(self):
        self.sip.receive(self.invite,'192.0.2.20')
        self.now[0] = 17
        self.sip.tick()
        self.assertIsNone(self.sip.dialog)

    def test_preview_200_ack_and_bye(self):
        self.sip.preview('192.0.2.20')
        invite = SIP.parse(self.out[-1][0])
        headers = {k:invite.headers[k] for k in ('via','from','to','call-id','cseq')}
        headers['to'] += ';tag=panel-tag'
        headers['content-type'] = 'application/sdp'
        reply = wire('SIP/2.0 200 OK',headers,'v=0\r\nm=audio 0 RTP/AVP 0\r\nm=video 5010 RTP/AVP 98\r\n')
        self.sip.receive(reply,'192.0.2.20')
        self.assertEqual(self.sip.dialog.phase,'early_video')
        self.assertTrue(SIP.parse(self.out[-1][0]).first.startswith('ACK '))
        self.sip.hangup()
        bye = SIP.parse(self.out[-1][0])
        self.assertTrue(bye.first.startswith('BYE '))
        self.assertEqual(bye.body,'reason:1')

    def test_unconfigured_peer_ignored(self):
        self.sip.receive(self.invite,'192.0.2.30')
        self.assertEqual(self.out,[])
