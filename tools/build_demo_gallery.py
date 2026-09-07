"""Build the offline gallery from real UI captures of the synthetic fixture."""
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTIONS = {
    'clock-editorial': ('书页时钟 · Editorial', '舒展的衬线数字与低对比度状态。'),
    'clock-digital': ('数字时钟 · Digital', '醒目的数字，适合远距离查看。'),
    'clock-analog': ('模拟时钟 · Analog', '刻度与指针；秒针可隐藏、跳动或平滑移动。'),
    'clock-nixie': ('电子管时钟 · Nixie', '由 CSS 绘制的暖色玻璃与发光数字。'),
    'clock-nixie-quiet': ('无秒显示 · Hidden seconds', '隐藏秒数，让空闲界面更安静。'),
    'phone-enrollment': ('话机授权 · Enrollment', '管理员选择设备名称与入口范围。'),
    'phone-preferences': ('话机偏好 · Preferences', '本机时钟、秒针、音量与入口预览。'),
    'phone-recent': ('最近活动 · Recent activity', '展开查看最近三项活动。'),
    'phone-preview': ('入口预览 · Preview', '完整保留 4:3 画面，操作浮在画面上。'),
    'phone-incoming': ('来访画面 · Incoming visit', '紧凑标题与大触控按钮，音乐按设定时长循环。'),
    'phone-ring-ended': ('响铃结束 · Ring window ended', '音乐停止后仍可查看画面和操作。'),
    'phone-muted': ('本次静音 · Muted visit', '只静音当前来访。'),
    'phone-portrait': ('竖屏平板 · Portrait tablet', '完整画面居中，保留必要留白。'),
    'phone-mobile': ('手机竖屏 · Narrow screen', '较窄屏幕仍保留完整画面与操作。'),
    'phone-wide': ('手机横屏 · Short landscape', '短横屏使用紧凑的覆盖控件。'),
    'phone-stale-video': ('画面过期 · Stale frame', '不把旧帧当成实时画面。'),
    'phone-offline': ('连接中断 · Offline', '状态清楚呈现，断线时禁用控制。'),
    'phone-revoked': ('授权撤销 · Revoked', '撤销后退出话机，重新授权才能使用。'),
    'admin-login': ('管理员登录 · Sign in', '独立的管理员登录入口。'),
    'admin-dashboard': ('管理首页 · Dashboard', '网关、入口、策略与活动概览。'),
    'admin-ringtone': ('内置铃声 · Built-in melodies', '管理员配置铃声及 15/30/45/60 秒时长。'),
    'admin-custom-music': ('自定义音乐 · Custom music', '导入、试听并保存自己的音乐。'),
    'admin-network': ('网关配置 · Configuration', '身份、接口与入口配置；保存不改变系统网卡地址。'),
    'admin-password': ('密码设置 · Password', '修改管理员密码。'),
    'admin-journal': ('事件日志 · Journal', '查询并导出网关活动记录。'),
    'admin-devices': ('设备管理 · Devices', '查看设备授权及其入口范围。'),
}


def main():
    folder = ROOT/'docs/demo'
    manifest = json.loads((folder/'manifest.json').read_text())
    images = {Path(item['file']).stem: item for item in manifest['images']}
    if images.keys() != CAPTIONS.keys():
        raise SystemExit('Every captured interface must have a caption')
    for file, digest in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/file).read_bytes()).hexdigest() != digest:
            raise SystemExit('Regenerate screenshots after source changes: '+file)
    for item in images.values():
        if hashlib.sha256((folder/item['file']).read_bytes()).hexdigest() != item['sha256']:
            raise SystemExit('Image hash mismatch: '+item['file'])
    intro = ('这些开发版预览由真实界面自动截图生成。住户、入口、视频与音频均为合成示例；'
             '目前部署版本仍为 v0.2.0。Screenshots show the development version using synthetic data.')
    markdown = ['# 界面图集 · Interface gallery', intro,
                '[中文手册](user-guide.zh-CN.md) · [English guide](user-guide.md) · [离线交互图集](demo/index.html)',
                '下载仓库后在浏览器打开 `docs/demo/index.html` 可切换预览。GitHub 页面可直接浏览以下全部截图。']
    buttons, figures = [], []
    for index, (key, (title, caption)) in enumerate(CAPTIONS.items()):
        filename = images[key]['file']
        markdown += ['## '+title, caption, f'![{title}](demo/{filename})']
        buttons.append(f'<button type="button" data-index="{index}" aria-pressed="{str(index == 0).lower()}">{html.escape(title)}</button>')
        figures.append(f'<figure id="view-{index}"'+(' hidden' if index else '')+f'><figcaption><h2>{html.escape(title)}</h2><p>{html.escape(caption)}</p></figcaption><a href="{filename}"><img src="{filename}" alt="{html.escape(title)}" loading="lazy"></a></figure>')
    markdown += ['## Reproduce', 'See [capture commands and test coverage](phone.md#display-and-ringing-preferences). Source and image hashes are recorded in [manifest.json](demo/manifest.json).']
    (ROOT/'docs/demo-gallery.md').write_text('\n\n'.join(markdown)+'\n')
    (folder/'index.html').write_text('''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fermax Lynx · 界面图集</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101d1c;color:#eceee6}*{box-sizing:border-box}body{margin:0}header{padding:28px 32px;border-bottom:1px solid #42534d}h1{font-size:32px;margin:0 0 12px}p{line-height:1.65;color:#b5c2b9}main{display:grid;grid-template-columns:280px minmax(0,1fr)}nav{padding:20px;display:grid;gap:8px;align-content:start;max-height:calc(100vh - 170px);overflow:auto;position:sticky;top:0}button{font:inherit;font-size:16px;text-align:left;color:inherit;border:1px solid #41514c;background:transparent;border-radius:8px;padding:12px;min-height:48px;cursor:pointer}button[aria-pressed=true]{background:#dbe9cd;color:#17231d}button:focus-visible,a:focus-visible{outline:3px solid #ebc777;outline-offset:3px}section{padding:24px;min-width:0}figure{margin:0}figure[hidden]{display:none}h2{margin:0;font-size:25px}img{display:block;max-width:100%;max-height:78vh;height:auto;width:auto;margin:20px auto;border:1px solid #41514c;border-radius:12px}a{color:#dbe9cd}@media(max-width:720px){main{display:block}nav{position:static;max-height:230px;grid-template-columns:repeat(2,minmax(0,1fr))}header,section{padding:20px}h1{font-size:27px}}
</style><header><h1>Fermax Lynx · 界面图集</h1><p>'''+html.escape(intro)+'''</p></header><main><nav aria-label="选择界面">'''+''.join(buttons)+'''</nav><section aria-live="polite">'''+''.join(figures)+'''</section></main><script>
document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('nav button').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));document.querySelectorAll('figure').forEach((figure,index)=>figure.hidden=String(index)!==button.dataset.index)}));
</script></html>
''')
    print(f'Validated hashes and built {len(images)}-screen galleries')


if __name__ == '__main__':
    main()
