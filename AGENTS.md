# Development coordination

Read CONTRIBUTING.md and the linked Issue before editing. Use an independent checkout and a `codex/<task>` branch for each agent session. Never overwrite another session's uncommitted work.

## Claim work

Before editing code or an existing PR, explicitly claim its Issue with an agent/session identifier, branch/PR, scope and status. A shared GitHub assignee is not a unique agent identity. Check existing claims; resolve overlaps before modifying the same area. Link every PR to its coordinating Issue. Update status when blocked, changing scope or handing off; finish with validation and remaining work.

Maintainers using the owner's production gateway must first read the private companion repository's AGENTS.md and STATUS.md: `helixzz/fermax-lynx-internal` (authorized access required). Its task lock and environment lock are mandatory. Community contributors without access can work locally with synthetic tests; they must not access the maintainer's deployment or request private credentials in a public Issue.

## Live environments

Do not deploy, restart, capture traffic or perform live UI/SSH tests without a current exclusive environment claim under the deployment owner's coordination rules. A lease is not permission to actuate a physical lock. Preserve existing settings unless the owner requested changes. Record a backup, target commit, validation and rollback path privately for every deployment. Expired claims are not automatic permission to take over.

## Publication

Only general source, synthetic fixtures and documentation addresses belong here. Never commit real residence IDs, IP/MAC addresses, passwords, keys, captures, databases, private reports, video/images or vendor descriptor bundles. Inspect tracked files, staged diff, all commits being pushed and PR/Issue text. Private maintainers must also run the companion repository's `tools/check_public.py` against this checkout before publishing.

Run tests appropriate to the change. Changes to SIP, opening policy, authentication or request correlation require regression coverage. Tests must not contact a building network or operate locks. Do not claim physical opening from a successful API/SIP response alone.

The private repository is not an upstream branch: never merge, mirror or bulk-copy it here. Do not paste its content into public comments or CI logs.
