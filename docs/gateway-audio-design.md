# Gateway ringing: reviewed design

Issue [#10](https://github.com/helixzz/fermax-lynx-gateway/issues/10). Development after v0.4.0; not yet released.

The gateway is an independent bell, even with zero enrolled phones. It defaults on,
with 50% application gain and automatic routing. An explicit off setting persists.
It shares the existing melody and 15/30/45/60-second duration with phones, while
its switch, gain and output are independent. Changes apply to the next visit;
switching it off cancels current playback. A phone's mute does not mute the gateway.

Incoming call events deliver an immutable call ID, music snapshot and monotonic
deadline directly to a separate worker. State/SIP threads never enumerate devices,
render audio, open PCM or wait for playback. Call ending/answered events cancel the
worker, and duplicate IDs never start a second job. Late preparation checks the job
again. A service restart starts idle and never replays historical journal entries.
Automatic opening does not disable ringing; actual call lifecycle governs its end.

The headless Linux backend enumerates hardware playback PCMs from ALSA proc/sysfs,
not browser devices or virtual recording endpoints. `aplay` opens a specific
`plughw` endpoint without changing the OS default. Automatic selection orders USB,
analog, HDMI; other hardware remains manually selectable. Device preference keys
use physical identity (USB serial when available, otherwise physical port path),
not a volatile card number. Identical unnumbered USB devices remain port-dependent.
Names and actual output are shown separately from the saved preference.

A manually preferred device falls back through the automatic order when missing
or failing. Each candidate is attempted once per job; playback that is already
healthy does not jump to newly attached devices. Failure uses only remaining time.
Missing speakers, muted amplifiers and disconnected analog plugs cannot be inferred
from successful PCM writes: explicit short test sound and human listening are needed.
Device errors are retained per output; no background audible probes run.

One persistent `gateway-audio.json` backs authenticated Web endpoints and trusted
local LCD controls. Web keeps the existing restrained dark palette and grouped
settings navigation: Gateway sound, Shared melody, Phones, Configuration, Password.
The 480×320 framebuffer uses separate large-touch sound and output-selection pages.
Neither surface can silently change automatic opening when editing sound.

The test command plays a three-second built-in chime using saved route/gain,
requires ringing enabled and an idle call, and is preempted by an incoming call.
Stopping a test cannot stop a real visit. Opening either UI never produces sound.

Acceptance includes fake PCM/hotplug/failure backends, lifecycle and auth tests,
Web/LCD previews, and eventual physical USB/analog/HDMI tests where hardware exists.
Desktop sound servers that exclusively hold ALSA devices may need releasing the
chosen output; automatic desktop-session integration is outside this first backend.

References: [kernel ALSA proc files](https://www.kernel.org/doc./html/next/sound/designs/procfile.html),
[ALSA PCM API](https://www.alsa-project.org/alsa-doc/alsa-lib/pcm.html),
[Raspberry Pi audio configuration](https://www.raspberrypi.com/documentation/configuration/computers/raspberry-pi.html).
