# Versioning and releases

Use [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html), with Git tags
`vMAJOR.MINOR.PATCH` and the matching package version in `pyproject.toml`.
The compatibility surface includes documented HTTP endpoints and payloads, CLI
options, and persisted configuration/state formats. Internal Python objects and
observed vendor wire behavior are not a stable public API.

While the project is experimental (`0.x`):

- Increment MINOR for features or incompatible changes; reset PATCH to zero.
  Describe incompatible changes and migration/rollback limits in release notes.
- Increment PATCH for backward-compatible fixes and documentation-only releases.
- Use `v0.3.0-rc.1`, `-rc.2`, etc. for release candidates; the corresponding Python
  package version uses `0.3.0rc1`, `0.3.0rc2`, etc.
- Begin `1.0.0` when the supported API and operational baseline are declared stable.
  Thereafter, incompatible changes increment MAJOR, compatible features MINOR,
  and compatible fixes PATCH.

A version is immutable: never move a published tag or replace its source artifact.
A correction gets a new version. Publishing a 0.x release does not imply that all
hardware or endurance validation is complete; record the actual checks and gaps.
The repository's current default branch is the integration mainline, regardless
of its branch name. Release tags must reference a merged mainline commit.

## Release checklist

1. Claim the linked task, review the final diff, update the package version and
   `CHANGELOG.md`, and run the required tests and public-content check.
2. Merge the reviewed PR and verify CI for the resulting mainline commit. Keep
   incomplete feature or field-validation issues open.
3. Create an annotated tag for that exact commit. Publish a GitHub Release with
   feature changes, checks, known limits and upgrade/rollback notes. Publish only
   source from Git and checksums; exclude local state and deployment evidence.
4. Deployment is a separate authorized operation. Claim the environment, confirm
   no call, back up code and private state, deploy the tagged source, and verify
   health and preserved settings. Record the exact commit and rollback location
   privately; see [deployment](deployment.md).

The original source declared package version 0.1.0 without a published release.
The first tagged release is 0.2.0; do not retroactively invent a 0.1.0 release.
