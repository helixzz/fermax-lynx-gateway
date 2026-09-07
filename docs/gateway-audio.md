# 网关独立响铃 · Gateway sound

v0.5.0 起提供。网关可以独立发出来访铃声，
即使没有登记话机、话机离线或浏览器全部关闭。它不提供双向通话。

## 设置入口

Web 管理员登录后，进入 **设备与密码设置 → 网关声音**。
实体触摸屏进入 **设置 → 声音与扬声器**。
两端保存同一份设置，修改会同步；不需要给网关登记一个“话机”。

![网关声音设置，合成设备](demo/admin-gateway-sound.webp)

| 设置 | 默认及行为 |
|---|---|
| 呼入响铃 | 默认开启；关闭立即停止当前声音，关闭状态跨重启保留 |
| 音量 | 50%，只调整本应用的播放增益；新值用于下一次来访 |
| 音频输出 | 自动：USB → 3.5mm 模拟 → HDMI，只使用存在的设备 |
| 音乐与时长 | 与话机共用；在“共用铃声”选择 16 首音乐或上传自己的音乐，15/30/45/60 秒，默认 30 秒 |
| 测试声音 | 按已保存的输出和音量播放三秒门铃；不是所选整首音乐的试听 |

“共用铃声”页的试听在当前浏览器播放；“网关声音”页的测试从网关扬声器播放。
改了输出但还没保存时，测试仍使用已保存设置。浏览/刷新设备列表不会自动发声。
实体屏幕的按钮直接保存开关、音量与输出；Web 表单需点击保存。

![实体声音设置](demo/lcd-sound.webp)
![实体输出选择](demo/lcd-outputs.webp)

## 自动选择与设备断开

可手动指定首选设备。首选失联或无法播放时，按 USB、模拟、HDMI 顺序尝试其他输出，
界面显示实际输出与降级状态，并保留你的首选偏好。正在正常播放时插入 USB，
不会打断当前扬声器；下一次来访重新选择。拔出正在使用的设备后，降级只播放剩余时长。
每个设备每次来访最多尝试一次，总尝试不超过八个。

![首选设备失联](demo/admin-gateway-no-device.webp)

设备标识不依赖易变化的声卡编号；无序列号的相同 USB 设备按物理端口区分，
换插口后可能需要重新手选。列表中的“已检测”不是实际出声保证：模拟接口可能没有接音箱，
显示器也可能没有扬声器。请在没有来访时主动测试，并检查外接扬声器音量、电源及系统静音。

没有可用设备、声卡被其他程序占用或无权限时，响铃状态会提示故障，门禁与视频继续运行。
一个话机的静音不会关闭网关；关闭网关也不影响话机响铃。自动开门仍启用时也会响铃，
以实际来访结束或设定时限为准；主动预览不会响铃。来访结束、挂断或接听时停止声音。

## 安装与维护

Linux 安装 `alsa-utils`，运行服务的用户需有播放设备访问权限（通常为 `audio` 组）。
仓库中的 systemd 示例含 `SupplementaryGroups=audio`；定制服务需自行核对，不能盲目覆盖。
无需桌面登录，应用不会改变全局默认声卡或网络设置。
桌面音频服务器若独占硬件输出，需要先解决设备占用；首版不自动控制桌面会话音频服务。

新的私有文件 `gateway-audio.json` 应随完整状态一起备份。
首次升级到此功能时默认开启：若有可用输出，下一次呼入可能响铃。
已明确关闭的设置不会被正常升级重置。损坏的声音配置只会暂停网关声音，
两端重新保存有效设置即可恢复，不应为此恢复旧密码或设备授权。
回滚到 v0.4.0 会失去网关本机声音，保留该配置文件供后续升级使用。

当前仅完成合成音频后端、Web/实体触摸操作和画面验证；USB、模拟、HDMI 的实际出声、
硬件热插拔及旧平板声音仍须有对应硬件后验收。画面中的名称和设备均为合成示例。

## English quick guide

Available in v0.5.0. The gateway rings independently of all
browser phones, defaults on, and has its own 50% gain and output preference. Open
administrator settings → 网关声音, or LCD settings → 声音与扬声器. Both edit the same
persistent configuration. Web changes require Save; LCD buttons save immediately.
Melody and duration are shared with phones in 共用铃声; each visit freezes them.

Automatic routing prefers USB, then analog, then HDMI. A manual preference falls
back when unavailable without discarding the preference. A healthy playing device
is not switched mid-visit. A disconnected output can fall back for only the remaining
time. Hardware enumeration cannot confirm a connected, audible speaker: use the
explicit three-second gateway test with saved settings. Browser melody audition
plays on the browser instead. Calls preempt tests; outgoing previews never ring.

Install `alsa-utils` and give the service user audio-device access. Back up
`gateway-audio.json` with private state; never publish it. Defaults may enable sound
on the first upgrade, while an explicit disabled value persists. Code rollback to
v0.4.0 removes gateway ringing without requiring a state restore. Real hardware
output/permission/hotplug acceptance remains open; the test fixture uses a silent
backend and never accesses an actual speaker or building network.
