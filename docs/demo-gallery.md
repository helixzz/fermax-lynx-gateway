# 界面图集 · Interface gallery

这些开发版预览由真实界面自动截图生成。住户、入口、视频与音频均为合成示例；目前部署版本仍为 v0.2.0。Screenshots show the development version using synthetic data.

[中文手册](user-guide.zh-CN.md) · [English guide](user-guide.md) · [离线交互图集](demo/index.html)

下载仓库后在浏览器打开 `docs/demo/index.html` 可切换预览。GitHub 页面可直接浏览以下全部截图。

## 书页时钟 · Editorial

舒展的衬线数字与低对比度状态。

![书页时钟 · Editorial](demo/clock-editorial.webp)

## 数字时钟 · Digital

醒目的数字，适合远距离查看。

![数字时钟 · Digital](demo/clock-digital.webp)

## 模拟时钟 · Analog

刻度与指针；秒针可隐藏、跳动或平滑移动。

![模拟时钟 · Analog](demo/clock-analog.webp)

## 电子管时钟 · Nixie

由 CSS 绘制的暖色玻璃与发光数字。

![电子管时钟 · Nixie](demo/clock-nixie.webp)

## 无秒显示 · Hidden seconds

隐藏秒数，让空闲界面更安静。

![无秒显示 · Hidden seconds](demo/clock-nixie-quiet.webp)

## 话机授权 · Enrollment

管理员选择设备名称与入口范围。

![话机授权 · Enrollment](demo/phone-enrollment.webp)

## 话机偏好 · Preferences

本机时钟、秒针、音量与入口预览。

![话机偏好 · Preferences](demo/phone-preferences.webp)

## 最近活动 · Recent activity

展开查看最近三项活动。

![最近活动 · Recent activity](demo/phone-recent.webp)

## 入口预览 · Preview

完整保留 4:3 画面，操作浮在画面上。

![入口预览 · Preview](demo/phone-preview.webp)

## 来访画面 · Incoming visit

紧凑标题与大触控按钮，音乐按设定时长循环。

![来访画面 · Incoming visit](demo/phone-incoming.webp)

## 响铃结束 · Ring window ended

音乐停止后仍可查看画面和操作。

![响铃结束 · Ring window ended](demo/phone-ring-ended.webp)

## 本次静音 · Muted visit

只静音当前来访。

![本次静音 · Muted visit](demo/phone-muted.webp)

## 竖屏平板 · Portrait tablet

完整画面居中，保留必要留白。

![竖屏平板 · Portrait tablet](demo/phone-portrait.webp)

## 手机竖屏 · Narrow screen

较窄屏幕仍保留完整画面与操作。

![手机竖屏 · Narrow screen](demo/phone-mobile.webp)

## 手机横屏 · Short landscape

短横屏使用紧凑的覆盖控件。

![手机横屏 · Short landscape](demo/phone-wide.webp)

## 画面过期 · Stale frame

不把旧帧当成实时画面。

![画面过期 · Stale frame](demo/phone-stale-video.webp)

## 连接中断 · Offline

状态清楚呈现，断线时禁用控制。

![连接中断 · Offline](demo/phone-offline.webp)

## 授权撤销 · Revoked

撤销后退出话机，重新授权才能使用。

![授权撤销 · Revoked](demo/phone-revoked.webp)

## 管理员登录 · Sign in

独立的管理员登录入口。

![管理员登录 · Sign in](demo/admin-login.webp)

## 管理首页 · Dashboard

网关、入口、策略与活动概览。

![管理首页 · Dashboard](demo/admin-dashboard.webp)

## 内置铃声 · Built-in melodies

管理员配置铃声及 15/30/45/60 秒时长。

![内置铃声 · Built-in melodies](demo/admin-ringtone.webp)

## 自定义音乐 · Custom music

导入、试听并保存自己的音乐。

![自定义音乐 · Custom music](demo/admin-custom-music.webp)

## 网关配置 · Configuration

身份、接口与入口配置；保存不改变系统网卡地址。

![网关配置 · Configuration](demo/admin-network.webp)

## 密码设置 · Password

修改管理员密码。

![密码设置 · Password](demo/admin-password.webp)

## 事件日志 · Journal

查询并导出网关活动记录。

![事件日志 · Journal](demo/admin-journal.webp)

## 设备管理 · Devices

查看设备授权及其入口范围。

![设备管理 · Devices](demo/admin-devices.webp)

## Reproduce

See [capture commands and test coverage](phone.md#display-and-ringing-preferences). Source and image hashes are recorded in [manifest.json](demo/manifest.json).
