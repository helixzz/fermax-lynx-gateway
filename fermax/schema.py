"""Minimal wire field definitions for implemented interoperability operations.

Only field identifiers and types used by this client are described here; this is
not a copy of the vendor's complete descriptor set or application distribution.
"""
from google.protobuf import descriptor_pb2 as pb


def files():
    f = pb.FileDescriptorProto(name='gateway_wire.proto', package='protobuffers', syntax='proto2')
    def message(name, fields=(), extensible=False):
        m=f.message_type.add(name=name)
        if extensible:
            m.extension_range.add(start=100,end=536870912)
        for number,name,kind,repeated,type_name in fields:
            field=m.field.add(name=name,number=number,type=kind,label=3 if repeated else 1)
            if type_name:
                field.type_name='.protobuffers.'+type_name
        return m
    message('Message',[(1,'uuid',12,False,None)],True)
    for name in ('Command','Response','Event'):
        message(name,extensible=True)
    def extension(parent,name,number,child):
        f.extension.add(name=name,number=number,label=1,type=11,
                        extendee='.protobuffers.'+parent,type_name='.protobuffers.'+child)
    for number,kind in ((100,'command'),(101,'response'),(102,'event')):
        extension('Message',kind,number,kind.title())
    enum=f.enum_type.add(name='PanelOpenDoorResultEnum')
    enum.value.add(name='PANEL_OPEN_DOOR_RESULT_OK',number=0)
    enum.value.add(name='PANEL_OPEN_DOOR_RESULT_ERROR',number=1)
    protocol=f.enum_type.add(name='SIPProtocol')
    for number,name in enumerate(('STANDARD','LYNX','PUSH')):
        protocol.value.add(name=name,number=number)
    message('IPAddressProtocol',[(1,'ip_address',9,False,None),(2,'protocol',14,False,'SIPProtocol'),
                                 (4,'delete',8,False,None),(5,'extension',5,False,None)])
    definitions = [
        ('Command','panelGetRelaysCommand',1301,[(1,'doormatic',8,False,None)]),
        ('Response','panelGetRelaysResponse',1301,[(1,'relayTags',9,True,None)]),
        ('Command','panelGetAllowOpenDoorFlagCommand',1302,[(1,'dummy',8,False,None)]),
        ('Response','panelGetAllowOpenDoorFlagResponse',1302,[(1,'allowOpenDoor',8,False,None)]),
        ('Command','panelOpenDoorCommand',1300,[(1,'relayName',9,False,None),(2,'doormatic',8,False,None),(3,'pmuTag',9,False,None)]),
        ('Response','panelOpenDoorResponse',1300,[(1,'result',14,False,'PanelOpenDoorResultEnum')]),
        ('Command','sessionKeepAliveCommand',2301,[(1,'dummy',8,False,None)]),
        ('Response','sessionKeepAliveResponse',2301,[(1,'state',8,False,None)]),
        ('Event','panelCapabilitiesEvent',1300,[(1,'openDoorEnable',8,False,None)]),
        ('Command','pushDeviceCallCommand',3005,[(1,'pushType',9,False,None),(2,'ip',9,False,None)]),
        ('Event','notifyIPProtocolEvent',3003,[(1,'ipAdresses',11,True,'IPAddressProtocol'),
            (2,'block',5,False,None),(3,'unit',9,False,None),(4,'gateway',9,False,None)]),
    ]
    for parent,name,number,fields in definitions:
        child=name[0].upper()+name[1:]
        message(child,fields)
        extension(parent,name,number,child)
    return [f]
