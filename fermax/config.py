"""Site-specific configuration. No real installation defaults belong here."""
import copy
import ipaddress
import json
import re
from pathlib import Path

EXAMPLE = {
    'building':'Example building', 'unit':'0101', 'extension':0,
    'monitor_ip':'192.0.2.10', 'building_interface':'eth0',
    'home_interface':'wlan0', 'web_port':8765,
    'panels':[{'id':'entrance', 'name':'Entrance', 'ip':'192.0.2.20'}],
}


def validate(value):
    if not isinstance(value, dict) or set(value) != set(EXAMPLE):
        raise ValueError('配置字段不完整或含未知字段')
    result = copy.deepcopy(value)
    for key in ('building','unit'):
        if not isinstance(result[key],str) or not 1 <= len(result[key]) <= 48 or any(ord(c)<32 for c in result[key]):
            raise ValueError('楼号和门牌号应为 1–48 字符的文本')
    if type(result['extension']) is not int or not 0 <= result['extension'] <= 7:
        raise ValueError('分机号范围为 0–7')
    if type(result['web_port']) is not int or not 1024 <= result['web_port'] <= 65535:
        raise ValueError('网站端口范围为 1024–65535')
    for key in ('building_interface','home_interface'):
        if not isinstance(result[key],str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}',result[key]):
            raise ValueError('网络接口名称无效')
    if result['home_interface'] == result['building_interface']:
        raise ValueError('家庭网络和门禁网络需使用不同接口')
    def address(raw):
        if not isinstance(raw,str):
            raise ValueError('IP 地址应为文本')
        ip = ipaddress.IPv4Address(raw)
        if ip.is_multicast or ip.is_unspecified or ip.is_loopback or int(ip)==0xffffffff:
            raise ValueError('设备 IP 地址无效')
        return str(ip)
    result['monitor_ip'] = address(result['monitor_ip'])
    panels = result['panels']
    if not isinstance(panels,list) or not 1 <= len(panels) <= 8:
        raise ValueError('请配置 1–8 个门口机')
    ids, ips = set(), {result['monitor_ip']}
    for panel in panels:
        if not isinstance(panel,dict) or set(panel) != {'id','name','ip'}:
            raise ValueError('门口机需要 id、name、ip')
        if not isinstance(panel['id'],str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',panel['id']) or panel['id'] in ids:
            raise ValueError('门口机 ID 无效或重复')
        if not isinstance(panel['name'],str) or not 1<=len(panel['name'])<=48 or any(ord(c)<32 for c in panel['name']):
            raise ValueError('门口机名称无效')
        panel['ip'] = address(panel['ip'])
        if panel['ip'] in ips:
            raise ValueError('设备 IP 地址重复')
        ids.add(panel['id'])
        ips.add(panel['ip'])
    return result


def load(path):
    path = Path(path)
    if not path.exists():
        raise ValueError('缺少 config.json，请先运行 python -m fermax.admin init')
    return validate(json.loads(path.read_text(encoding='utf-8-sig')))
