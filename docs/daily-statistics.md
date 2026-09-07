# 今日活动 · Daily activity

管理员概览和树莓派实体首页显示今日来电、已确认开门。话机待机时钟下用门铃与门扇图标加数字展示相同指标；轻触或键盘聚焦图标可查看含义。操作面板也有文字说明。常用状态、静音和收起操作使用统一描边图标；开门、结束来访等关键操作仍保留文字。

![管理员今日统计](demo/admin-statistics.webp)
![话机待机统计](demo/phone-statistics.webp)
![实体首页](demo/lcd-home.webp)

## 怎样计数

- **来电**：网关收到的唯一呼入来访，包含未接来访；不是接听语音次数。主动预览不计，多个话机不会使同一来访重复增加。
- **已确认开门**：门口机返回成功的手动和自动开门确认。请求排队、失败、拒绝、超时或结果未知不计；这个数字不代表门磁或物理开门检测。
- 同一来电按 `call_id` 去重。手动确认按 `request_id` 去重，同次来访中的不同手动请求可分别计数；自动确认按 `call_id` 去重。重复事件归首次记录的日期，跨午夜重传不增加次日数字。
- 日期采用**网关操作系统本地日期**，从当地午夜至次日午夜，支持夏令时。浏览器时区不会改变统计；网关未对时会显示提示，时钟校正可能改变事件所属日期。没有另外配置统计时区或重置按钮。
- 管理员汇总全部日志中的入口。每台话机仅接收其获授权入口的汇总，不能查看其他入口的计数或统计明细。改变授权范围后汇总随之变化。
- 统计保存在现有事件数据库的派生表中，重启保留。升级首次回填已有日志；旧记录缺少可靠 ID 时逐条计数，可能包含无法消除的历史重复。缺少入口 ID 的旧记录只计入管理员汇总。
- 零次显示 **0**；断线或统计不可用显示 **—**，不会拿旧数字冒充今日数字。统计故障不阻断原有门禁控制。日志本身损坏仍需管理员排查；统计不承诺修复损坏数据库。LCD 超过四位显示 `9999+`，Web 和话机可查看完整数字。

## 升级与排查

无需安装新依赖或改门禁配置。升级前照常备份完整 `events.sqlite3` 及其一致性状态；新表 `activity_facts`、`activity_cursor` 均是派生数据，原始事件不被重写。旧版本忽略新增表，回滚后产生的事件会在再次升级时补入。首次回填时间随日志大小增长，服务启动前完成；不要手工删除原日志来“清零”。

若显示不可用，先检查连接及网关时间。持续不可用时由管理员检查数据库读取/写入权限、磁盘空间及日志完整性；修复底层故障后重启可继续回填。该功能不记录额外音视频、不新增外部统计服务，也不触发开门。

## English

The administrator Web overview and local LCD home show **today's incoming visits** and **confirmed openings**. The phone's idle screen uses a bell and a door icon with counts. Touch or focus an icon for its description; the controls panel also explains them. Common status/mute/collapse controls use consistent icons with accessible names. Opening and ending a visit retain visible text.

Incoming visits include unanswered calls, exclude outgoing previews and are deduplicated by `call_id`. Confirmed openings include successful manual and automatic protocol responses, not queued requests, denied/failed/unknown results or physical door-sensor observations. Manual confirmations use `request_id` (distinct requests during one visit count separately); automatic confirmations use `call_id`. Retransmissions belong to the first recorded event's day even across midnight.

Days follow the gateway OS local calendar, including 23/25-hour daylight-saving days, independently of the browser timezone. An unsynchronized-clock warning remains visible; clock corrections may change date attribution. Administrators see all journaled entrances; each phone receives only counts for its authorized entrances. No raw statistics details or other entrance totals are sent to phones.

Facts persist in the existing event database and are backfilled on upgrade without rewriting events. Legacy entries without reliable IDs count individually and may include historical duplicates; entries without an entrance ID are admin-only. Zero is `0`; disconnected/unavailable is `—`, never a stale daily count. LCD counts above 9999 use `9999+`; Web/phone retain full numbers. Optional statistics failure does not interrupt existing intercom control, but does not repair an already broken journal.

No new dependencies or control settings are needed. Back up the consistent event database before upgrading. Older versions ignore the derived `activity_facts` / `activity_cursor` tables; journal entries created after rollback are imported on a subsequent upgrade. Initial backfill runs before service startup and depends on log size. If unavailable persists, check disk space, database permissions and journal integrity; restart after resolving the cause. No media capture, external analytics or door action is added.
