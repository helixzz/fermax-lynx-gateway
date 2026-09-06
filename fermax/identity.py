"""Refresh only this household's protocol identity at configured entrance panels."""
import time


class Announcer:
    def __init__(self,transport,codec,config,notify,clock=time.monotonic):
        self.transport,self.codec,self.config,self.notify=transport,codec,config,notify
        self.clock=clock
        self.next_due=0
        self.waiting={}
        self.reported=set()

    def fields(self):
        address={'ip_address':self.config['monitor_ip'],'protocol':'LYNX','delete':False}
        if self.config['extension']:
            address['extension']=self.config['extension']
        return {'ipAdresses':[address],'block':self.config['block'],'unit':self.config['unit'],'gateway':''}

    def tick(self):
        now=self.clock()
        if now>=self.next_due:
            self.next_due=now+60
            for panel in self.config['panels']:
                address=(panel['ip'],56102)
                peer=self.transport.peers.get(address)
                if peer is None:
                    peer=self.transport.connect(*address)
                self.waiting[address]=(peer,now+5)
        for address,(peer,deadline) in list(self.waiting.items()):
            if address in self.transport.peers:
                self.transport.send(self.transport.peers[address],self.codec.envelope('event','notifyIPProtocolEvent',self.fields()))
                self.waiting.pop(address)
                if address not in self.reported:
                    self.reported.add(address)
                    self.notify('本户 LYNX 身份公告已发送','identity_announced',{'panel':address[0]})
            elif now>=deadline:
                peer.disconnect_now()
                self.waiting.pop(address)
                self.notify('身份公告连接超时，将在下一周期重试','identity_timeout',{'panel':address[0]})
