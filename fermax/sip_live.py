"""Observed LYNX SIP profile with bounded UDP transactions and one dialog."""
import re
import time
import uuid
from dataclasses import dataclass

from .protocol import SIP


def tag():
    return str(uuid.uuid4().int % 2147483646 + 1)


def wire(first, headers, body=''):
    encoded = body.encode('utf-8')
    headers = {**headers, 'Content-Length':str(len(encoded))}
    return (first+'\r\n'+''.join(f'{k}: {v}\r\n' for k,v in headers.items())+'\r\n').encode()+encoded


@dataclass
class Dialog:
    cid: str
    remote: str
    local_header: str
    remote_header: str
    incoming: bool
    created: float
    seq: int
    phase: str = 'ringing'
    acked: bool = False


class Signaling:
    def __init__(self, own, panels, send, notify, clock=time.monotonic, unit=''):
        self.own, self.panels = own, set(panels)
        self.send, self.notify, self.clock = send, notify, clock
        self.user_agent = (unit+' ' if unit else '')+'FermaxGateway'
        self.dialog = None
        self.pending = None
        self.cache = {}
        self.ack_response = None
        self.invites = {}
        self.cleanup = {}

    def sdp(self, audio=False):
        session = int(time.time())+2208988800
        return '\r\n'.join(['v=0', f'o=- {session} {session} IN IP4 {self.own}', 's=-',
            f'c=IN IP4 {self.own}', 't=0 0', f'm=audio {16400 if audio else 0} RTP/AVP 0 101',
            'a=rtpmap:0 PCMU/8000', 'a=ptime:20' if audio else 'a=ptime:0', 'a=rtpmap:101 telephone-event/8000',
            'a=fmtp:101 0-15', 'm=video 16402 RTP/AVP 98', 'a=rtpmap:98 H264/90000', ''])

    def response(self, sip, remote, status, reason, body='', local=None):
        headers = {'Via':sip.headers['via'], 'To':local or sip.headers['to'],
                   'From':sip.headers['from'], 'CSeq':sip.headers['cseq'], 'Call-ID':sip.headers['call-id']}
        if status >= 180:
            headers['Contact'] = f'<sip:{self.own}:5060>'
        if body:
            headers['Content-Type'] = 'application/sdp'
        result = wire(f'SIP/2.0 {status} {reason}', headers, body)
        self.send(result, remote)
        return result

    def request(self, method, body='', initial=False, seq=None):
        d = self.dialog
        if d is None:
            raise ValueError('No call')
        if seq is None:
            d.seq += 1
            seq = d.seq
        headers = {'Via':f'SIP/2.0/UDP {self.own}:5060;branch=z9hG4bK{tag()}',
            'To':d.remote_header, 'From':d.local_header, 'Call-ID':d.cid,
            'CSeq':f'{seq} {method}', 'Max-Forwards':'70', 'User-Agent':self.user_agent,
            'Contact':f'<sip:{self.own}:5060>'}
        if body:
            headers['Content-Type'] = 'text/plain' if method == 'BYE' else 'application/sdp'
        if initial:
            headers['Expires'] = '120'
        uri = f'sip:{d.remote}' if initial else f'sip:{d.remote}:5060'
        request = wire(f'{method} {uri} SIP/2.0', headers, body)
        self.send(request, d.remote)
        if method != 'ACK':
            self.pending = {'wire':request,'seq':str(seq),'method':method,'next':self.clock()+0.5,
                            'delay':0.5,'deadline':self.clock()+16,'provisional':False}
        if method == 'INVITE':
            self.invites[(d.cid,str(seq))] = {'wire':request,'remote':d.remote,
                'expires':self.clock()+300,'abandoned':False,'closed':False}
        return request

    def preview(self, remote):
        if remote not in self.panels or self.dialog:
            raise ValueError('已有通话或门口机无效')
        self.dialog = Dialog(tag()+'@'+self.own, remote, f'<sip:{self.own}>;tag={tag()}',
                             f'<sip:{remote}>', False, self.clock(), int(time.time()))
        self.request('INVITE', self.sdp(), initial=True)
        self.notify('outgoing', remote)

    def answer(self):
        if not self.dialog or self.dialog.phase != 'early_video' or self.pending:
            raise ValueError('当前无法接听')
        self.request('INVITE', self.sdp(audio=True))

    def hangup(self):
        if not self.dialog:
            return
        if self.dialog.phase == 'ringing' and not self.dialog.incoming:
            self.end('Cancelled')
            return
        if self.pending:
            raise ValueError('信令事务进行中，请稍后挂断')
        self.request('BYE', 'reason:1')
        self.dialog.phase = 'ending'
        self.notify('ending', self.dialog.remote)

    def end(self, reason):
        remote = self.dialog.remote if self.dialog else None
        if self.dialog:
            for (cid,seq), invite in self.invites.items():
                if cid == self.dialog.cid:
                    invite['abandoned'] = True
                    invite['closed'] = reason.startswith('BYE')
            if self.pending and self.pending['method']=='INVITE':
                original = SIP.parse(self.pending['wire'])
                headers = {k:original.headers[k] for k in ('via','to','from','call-id')}
                headers['CSeq'] = self.pending['seq']+' CANCEL'
                data = wire('CANCEL '+original.first.split()[1]+' SIP/2.0',headers)
                self.send(data,remote)
                self.cleanup[self.dialog.cid] = {'wire':data,'remote':remote,'seq':self.pending['seq'],
                    'method':'CANCEL','deadline':self.clock()+16,'next':self.clock()+.5,'delay':.5}
        self.dialog, self.pending, self.ack_response = None, None, None
        self.notify('ended', {'remote':remote,'reason':reason})

    def retired_response(self, sip, remote, cid, seq, method):
        """ACK late INVITE finals and tear down only our abandoned dialogs."""
        if method in ('BYE','CANCEL') and cid in self.cleanup and remote == self.cleanup[cid]['remote']:
            if method==self.cleanup[cid]['method'] and seq == self.cleanup[cid]['seq'] and int(sip.first.split()[1])>=200:
                self.cleanup.pop(cid)
                return True
        entry = self.invites.get((cid,seq)) if method=='INVITE' else None
        if not entry or not entry['abandoned'] or entry['remote']!=remote:
            return False
        status = int(sip.first.split()[1])
        if status<200:
            return True
        original = SIP.parse(entry['wire'])
        headers = {'Via':original.headers['via'] if status>=300 else f'SIP/2.0/UDP {self.own}:5060;branch=z9hG4bK{tag()}',
            'From':original.headers['from'],'To':sip.headers['to'],'Call-ID':cid,'CSeq':seq+' ACK'}
        uri = original.first.split()[1] if status>=300 else f'sip:{remote}:5060'
        self.send(wire(f'ACK {uri} SIP/2.0',headers),remote)
        if status<300 and not entry['closed']:
            entry['closed'] = True
            headers['Via'] = f'SIP/2.0/UDP {self.own}:5060;branch=z9hG4bK{tag()}'
            headers['CSeq'] = str(int(seq)+1)+' BYE'
            headers['Content-Type'] = 'text/plain'
            data = wire(f'BYE {uri} SIP/2.0',headers,'reason:1')
            self.send(data,remote)
            self.cleanup[cid] = {'wire':data,'remote':remote,'seq':str(int(seq)+1),
                'method':'BYE','deadline':self.clock()+16,'next':self.clock()+.5,'delay':.5}
        return True

    def receive(self, data, remote):
        if remote not in self.panels:
            return
        sip = SIP.parse(data)
        method = sip.first.split()[0]
        cid = sip.headers['call-id']
        seq, cseq_method = sip.headers['cseq'].split()
        if method=='SIP/2.0' and self.retired_response(sip,remote,cid,seq,cseq_method):
            return
        cache_key = (remote, cid, sip.headers.get('via'), sip.headers['cseq'])
        if method != 'SIP/2.0' and cache_key in self.cache:
            self.send(self.cache[cache_key][1], remote)
            return
        if method == 'INVITE':
            uri = sip.first.split()[1]
            target = uri[4:].split('@')[-1].split(';')[0].split(':')[0] if uri.startswith('sip:') else ''
            if target != self.own:
                self.response(sip, remote, 404, 'Not Found')
                return
            if self.dialog and (self.dialog.cid != cid or self.dialog.remote != remote):
                self.response(sip, remote, 486, 'Busy Here')
                return
            initial = self.dialog is None
            if initial:
                self.dialog = Dialog(cid, remote, sip.headers['to']+';tag='+tag(), sip.headers['from'],
                                     True, self.clock(), int(time.time()))
                self.response(sip, remote, 100, 'Trying')
                self.response(sip, remote, 180, 'Ringing', local=self.dialog.local_header)
                self.notify('incoming', remote)
            d = self.dialog
            audio = (sip.audio_port or 0) > 0
            # An unsolicited audio offer is not consent to activate the microphone.
            if audio and d.phase != 'audio':
                audio = False
            answer = self.response(sip, remote, 200, 'OK', self.sdp(audio), local=d.local_header)
            self.cache[cache_key] = (self.clock()+40, answer)
            self.ack_response = {'wire':answer,'next':self.clock()+0.5,'deadline':self.clock()+16,'seq':seq}
            d.phase = 'audio' if audio else 'early_video'
            self.notify(d.phase, remote)
        elif method == 'OPTIONS':
            self.response(sip, remote, 200, 'OK')
        elif method in ('BYE','CANCEL'):
            if not self.dialog or self.dialog.cid != cid or self.dialog.remote != remote:
                self.response(sip, remote, 481, 'Call Does Not Exist')
                return
            answer = self.response(sip, remote, 200, 'OK', local=self.dialog.local_header)
            self.cache[cache_key] = (self.clock()+40, answer)
            self.end(method)
        elif self.dialog and self.dialog.cid == cid and self.dialog.remote == remote:
            d = self.dialog
            if method == 'ACK':
                if self.ack_response and seq == self.ack_response['seq']:
                    self.ack_response = None
                    d.acked = True
            elif method == 'SIP/2.0':
                status = int(sip.first.split()[1])
                p = self.pending
                if not p or seq != p['seq'] or cseq_method != p['method']:
                    if 200 <= status < 300 and cseq_method == 'INVITE' and d.acked:
                        self.request('ACK', seq=int(seq))
                    return
                if status < 200:
                    p['provisional'] = True
                    return
                self.pending = None
                if cseq_method == 'INVITE':
                    d.remote_header = sip.headers['to']
                    if status < 300:
                        self.request('ACK', seq=int(seq))
                    else:
                        original = SIP.parse(p['wire'])
                        headers = {'Via':original.headers['via'], 'To':sip.headers['to'],
                                   'From':d.local_header, 'Call-ID':d.cid, 'CSeq':seq+' ACK'}
                        self.send(wire(f'ACK sip:{remote}:5060 SIP/2.0', headers), remote)
                    if status < 300:
                        d.acked = True
                        d.phase = 'audio' if (sip.audio_port or 0) > 0 else 'early_video'
                        self.notify(d.phase, remote)
                    elif d.phase == 'ringing':
                        self.end(f'SIP {status}')
                    else:
                        self.notify('error', f'接听失败 SIP {status}')
                elif cseq_method == 'BYE':
                    self.end(f'BYE {status}')

    def tick(self):
        now = self.clock()
        self.invites = {k:v for k,v in self.invites.items() if v['expires']>now}
        for cid, pending in list(self.cleanup.items()):
            if now>=pending['deadline']:
                self.cleanup.pop(cid)
            elif now>=pending['next']:
                self.send(pending['wire'],pending['remote'])
                pending['delay'] = min(4,pending['delay']*2)
                pending['next'] = now+pending['delay']
        self.cache = {k:v for k,v in self.cache.items() if v[0] > now}
        if self.pending:
            p = self.pending
            if now >= p['deadline']:
                self.end('SIP timeout')
            elif now >= p['next'] and not (p['method']=='INVITE' and p['provisional']):
                self.send(p['wire'], self.dialog.remote)
                p['delay'] = min(4, p['delay']*2)
                p['next'] = now+p['delay']
        if self.ack_response and self.dialog:
            if now >= self.ack_response['deadline']:
                self.end('ACK timeout')
            elif now >= self.ack_response['next']:
                self.send(self.ack_response['wire'], self.dialog.remote)
                self.ack_response['next'] = now+1
        if self.dialog and now-self.dialog.created > 180 and self.dialog.phase != 'ending':
            if self.dialog.acked and not self.pending:
                self.hangup()
            else:
                self.end('Maximum call duration')
