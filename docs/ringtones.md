# Ringtone library · 铃声来源与编排

Version 0.4.0 contains 16 short, AI-assisted project-original scores,
released with the project under [MIT](../LICENSE). They are locally synthesized
instrumental phrases, not recordings downloaded from an AI music service. No
third-party song, recording, artist voice or sampled instrument is bundled.

## Source review (2026-09-07)

We evaluated free music sources before choosing project-original material:

- [Suno's official distribution guidance](https://help.suno.com/en/articles/2410177)
  limits free-plan songs to non-commercial use. We did not select songs from that tier.
- [Pixabay's license summary](https://pixabay.com/service/license-summary/)
  restricts standalone distribution. A reusable music library in a public source
  release needs a more specific permission assessment than use inside a video;
  no Pixabay files were downloaded or bundled.

These are selection decisions for this release, not a blanket conclusion about all
uses of either service. Future external tracks must have a per-track source,
author, download date, license and required attribution recorded before inclusion.

## Reproducible project sources

The canonical [score catalog](../fermax/web/ringtones.json) records each stable ID,
name, group, synthesized voice, tempo, notes, rhythm, creation date and license.
The author is the Fermax Lynx Gateway project, using AI-assisted note/arrangement
editing. Creation date: 2026-09-07. No external download date applies. The first
three IDs remain available for saved preferences from v0.3.0.

[ringtone.js](../fermax/web/ringtone.js) renders 24 kHz mono buffers on demand,
normalizes their peaks to 0.26 and keeps silent loop boundaries. This is peak
matching, not a claim of identical perceived loudness. The cache retains at most
two decoded/rendered tracks; silence/mute, hidden pages and expired visits stop
playback. No CDN, font service, remote audio request or account is required for
built-in music. Actual old-tablet performance and speaker output still need testing.

Download the checkout and open [the offline sound demo](demo/sound.html) to audition
each phrase without running a gateway. The administrator can also select and preview
all 16 options, then explicitly save the setting. Custom audio previews use up to
8 seconds; built-in previews play one phrase. Incoming ringing still loops for the
configured 15/30/45/60-second window.

| ID | 名称 | 风格 | 合成音色 | 单次片段（秒） |
|---|---|---|---|---|
| chime | 清脆门铃 | 门铃 | bell | 3.28 |
| harbor | 海港旋律 | 柔和 | soft | 4.93 |
| marimba | 木琴轻响 | 木琴 | wood | 4.15 |
| porch | 门廊晨光 | 门铃 | bell | 4.63 |
| glass | 玻璃风铃 | 门铃 | glass | 4.43 |
| welcome | 欢迎回家 | 门铃 | bell | 4.85 |
| morning | 清晨花园 | 柔和 | soft | 5.67 |
| moon | 月光小径 | 柔和 | soft | 5.49 |
| drift | 云间漫步 | 柔和 | glass | 5.87 |
| petal | 花瓣小调 | 柔和 | soft | 5.14 |
| bamboo | 竹影 | 木琴 | wood | 4.70 |
| pebble | 溪边石子 | 木琴 | wood | 4.43 |
| tea | 午后茶歇 | 木琴 | piano | 5.39 |
| spark | 星点 | 电子 | pluck | 4.05 |
| orbit | 环游 | 电子 | sine | 4.85 |
| pulse | 轻快讯息 | 电子 | pluck | 4.33 |

## Upgrade and code rollback

The catalog adds IDs but does not change the preferences schema or existing three
IDs. Version 0.3.0 cannot load a saved new ID: before a code downgrade, use the
administrator settings to select and save `chime`, `harbor`, `marimba` or an existing
`custom` track. Back up current state before any deployment; do not restore old
credentials or grants just to change the music selection.
