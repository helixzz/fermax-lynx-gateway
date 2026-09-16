# Call diagnostics / 通话诊断

In the administrator event journal, select **诊断记录** and refresh or load older records. `GET /v1/diagnostics?before=<id>&limit=100` offers the same paginated records to an administrator. The normal CSV export remains the permanent visitor journal; diagnostic records are a separate local database, limited to seven days and 10,000 rows. Back up the entire state directory before upgrading; older versions ignore `diagnostics.sqlite3`.

诊断记录按 `call_id` 关联：`sip` 表示信令收包、应答或结束；`control_sent` / `control_result` 表示控制查询和开门应答；`phone_stream` 表示服务器向已授权设备发送状态；`phone_client` 表示网页自身报告显示、前后台及铃声状态；`gateway_audio` 表示网关音频准备、播放进程启动和结束。SIP 原始 Call-ID 仅保存摘要。网页上报只接收固定字段和枚举，受授权范围与频率限制，不接受任意日志正文。

A sent stream does not prove the browser rendered it. A browser report is client-reported evidence, not proof of audible sound. Likewise, an ALSA player starting does not prove the speaker was audible. Background/locked browsers can suspend scripts entirely; a missing report is not evidence that there was no visitor. There is no background push or two-way browser audio in this release.

自动开门前的 doormatic 继电器查询等待最多 8 秒，给可靠传输及门口机处理留出时间；超时后不重发可能有副作用的应用命令。`PANEL_OPEN_DOOR_RESULT_OK` 仅表示门口机确认，不能证明电梯授权或门锁机械动作。电梯问题仍需结合现场反馈；不要因授权未知而自动补发开门命令。

When reporting a problem, record the approximate time, entrance, physical result, phone foreground/background state and speaker behavior. Share only sanitized summaries publicly. Local diagnostic records can identify devices and configured peers and belong in a private support channel.
