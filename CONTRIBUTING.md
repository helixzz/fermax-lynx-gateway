# Contributing

Use synthetic fixtures and reserved documentation addresses in tests. Do not attach deployment configuration, protocol keys, credentials, captures, private logs, media or vendor archives to issues or commits. Describe firmware/hardware compatibility without identifying a residence.

Run `python3 -m unittest discover -s tests -v`. Tests must not contact a building network or actuate a real lock. Add a test for changes to signaling, opening policy, credential handling or request deduplication. Keep live network access confined to the controller and explicit configured peers.

Webhook and MCP work begins from the roadmap proposals; these features are not part of the initial runtime. Discuss changes to the wire schema with minimal field descriptions and synthetic examples rather than distributing vendor binaries.
