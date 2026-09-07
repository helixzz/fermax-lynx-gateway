# Phone UI decisions and evaluation

This development iteration addresses clock variety, distance/touch readability,
administrator music settings and the small video region in the original phone page.
Screenshots come from the real application with a loopback fixture. See the
[full gallery](demo-gallery.md) and its [source/image manifest](demo/manifest.json).

## Chosen direction

A quiet, warm-green idle display becomes an edge-to-edge video surface on a visit.
The visual hierarchy comes from large primary text, muted secondary text and one
clear opening action. No remote font service or UI framework is required.

| Area | Evaluated options | Decision |
|---|---|---|
| Clock | One digital style; animated spectacle; a small set of distinct styles | Editorial, bold digital, analog and warm tube styles, stored per browser |
| Seconds | Always animated; hidden; selectable motion | Hidden/ticking/sweeping, with sweep limited to analog and reduced-motion respected |
| Video | Original 48vh region; crop-to-fill; fixed 4:3 card; full viewport with contain | Full viewport with `object-fit: contain`, no crop or stretch |
| Controls | Large fixed bars; hidden gesture-only controls; floating edge controls | Compact title and translucent bottom controls, always available during a visit |
| Portrait | Crop the sides to fill; letterbox | Letterbox, preserving the whole entrance view; landscape is recommended |
| Music | Arbitrary external URLs; browser-owned oscillators only; local controlled assets | Original built-in melodies plus one administrator-uploaded local track |
| Ring deadline | Restart on page load; timer from first display; gateway call age | Monotonic gateway call age plus elapsed browser time; reload cannot extend a visit |

At 1024×768, the image element now occupies the complete viewport. A 4:3 image fits
that viewport exactly; previously the container used 48vh. The translucent overlays
still cover small edge regions, so full image-element area is not a claim that every
pixel is unobscured. At 768×1024 and 390×844 the complete frame remains visible inside
letterboxing. Narrow and short landscape layouts are exercised separately.

## Readability and input

Phone body text is 20px, desktop call actions 23px, primary labels 28–34px, and most
secondary text 17–18px. Narrow layouts reduce selected secondary labels to 13–16px
while retaining 18px/72px call actions. Primary phone buttons are at least 60px high
(76px in the desktop video view). Muted text keeps a clear visual hierarchy; connection
errors receive a stronger accent. Focus outlines and native select labels remain.

Apple's [button guidance](https://developer.apple.com/design/human-interface-guidelines/buttons)
emphasizes generous hit regions, and its [typography guidance](https://developer.apple.com/design/human-interface-guidelines/typography)
emphasizes hierarchy and readable sizing. Web CSS pixels are not a claim of physical
point equivalence; actual old-tablet distance readability remains a field check.

## Media and motion

[WebKit's media policy](https://webkit.org/blog/6784/new-video-policies-for-ios/) requires
planning for an audio-enabling gesture. The page therefore offers explicit enable/test
controls, including during a visit. No microphone is requested. Browser audio is not
proof that the system speaker is audible or the device is not muted.

[AudioBufferSourceNode looping](https://developer.mozilla.org/en-US/docs/Web/API/AudioBufferSourceNode/loop)
allows a decoded short track to repeat until its scheduled stop. Loading consumes
remaining ringing time; mute, offline, call-end and cancelled loads cannot start a
late playback. The gateway supplies monotonic call age, and captures its music/duration for that visit. A refreshed or newly opened phone
receives the same plan and only the remaining visit window. New settings apply to
subsequent visits; an active custom track is pinned until the visit ends.

Custom input is decoded by the administrator browser, limited to 60 seconds/10 MB,
and converted to mono PCM before upload. The server independently validates a bounded
16-bit PCM WAV, removes metadata, uses a content digest for the filename and keeps
the current upload plus, temporarily, the track pinned by an active visit. The old
pinned file is no longer served after the visit and is cleaned at the next upload. No URL fetching or vendor audio is involved. Upload and
fsync do not hold the controller state lock; snapshots read a committed settings record.

The analog sweep redraws at about 12 frames/second only while the visible idle analog
clock needs it. Hidden pages, video mode and reduced-motion preferences avoid this
animation. Tube effects are static CSS. [Object fitting](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/object-fit)
provides the video scaling without introducing a crop gesture or another media pipeline.

## What the automated checks establish

Python checks cover settings validation/persistence, upload bounds and atomic failure,
admin-only writes, scoped read/revocation, call-age behavior and existing gateway
regressions. A deterministic JavaScript test checks looping, loading time, cancellation,
late failures and volume limits. Chromium and WebKit exercise the actual forms, music
import, all clocks, seconds, viewport sizes, ring expiry, expired-call reload, mute,
stale images, offline state and revocation.

These checks do not establish iPadOS 15 hardware compatibility, audible speaker output,
72-hour foreground endurance, physical door effects or background ringing. Those
remain field acceptance items in Issue #3.
