# Protocol implementation scope

This client implements a narrow observed LYNX profile, not SIP or RTP in their entirety.

- Whole SIP messages use the installation's supplied 24-byte 3DES key, ECB with block padding. SIP runs on UDP 5060. A single dialog supports incoming early video, outgoing preview, ACK, BYE, bounded retransmissions and timeouts.
- ENet carries encrypted protobuf controls on the configured building peers. Common services are UDP 52102 (control), 56102 (notifications) and 57703 (keepalive). The minimal source schema covers only door relay/permission/opening, keepalive, capabilities and call notifications.
- A request UUID is not necessarily echoed in its response. Correlation uses the peer and expected response type, with one outstanding request per peer. Timeout closes that connection; opening is not automatically retried.
- Initial discovery (`panelGetRelaysCommand` with `doormatic=false`, then `panelGetAllowOpenDoorFlagCommand`) has at most three connection attempts and a twelve-second total budget starting at SIP ACK. Each handshake/query has a three-second limit, additionally bounded by that total budget. Recovery discards prior capabilities and repeats both reads on a fresh control ENet host; keepalive uses a separate unchanged host. Retired host events and responses cannot complete new requests. Call termination/network teardown cancels recovery. Once discovery finishes, control disconnection disables opening without replaying commands. The `doormatic=true` relay query and actual opening commands are excluded from retries even when their outcome is unknown.
- Wait for SIP ACK before starting application keepalive/control. Remove closed ENet peers from the connection index before a subsequent call. Both sequencing rules have regression coverage.
- The observed video profile uses a plain 12-byte RTP header, payload type 98, encrypted payload and H.264 single NAL units. Video is decoded into JPEG snapshots; this is not a full low-latency streaming player. Other packetization, codecs and loss recovery need more work.
- Incoming video can be established without negotiating audio. Automatic opening waits for the configured policy, established dialog and panel permission; preview alone never triggers it. No arbitrary elevator-floor command exists in this project.

The public schema contains manually expressed field numbers/types for implemented operations, not a redistributed vendor descriptor bundle. Unknown fields/messages are not interpreted. No captured packet, firmware, key, residence IP or real identity is included in the public tests.

The extension and apartment mapping seen at one site is not sufficient evidence for a universal IP formula; explicit monitor/panel addresses remain required. Interoperability and long-running reliability must be validated separately at each deployment.

The gateway announces only its configured block, apartment, extension and IP to configured panels at startup and every 60 seconds. The numeric protocol block is separate from the display label. This matches one observed installation; directory behavior elsewhere may differ.

Outgoing preview timeout sends CANCEL with the original transaction identifiers. Late final responses to abandoned invitations are acknowledged; late successful dialogs are immediately ended with BYE, without changing a newer call. Retired transactions remain tracked for five minutes. This prevents abandoned previews from leaving pending dialogs on the entrance panel.
