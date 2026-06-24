# Security Policy

## Supported Versions

This project is a patch that targets **UniFi Protect's bundled `service.js`**, so "supported"
is defined by the UniFi Protect build the patch is validated against — not by a release number
of this repo (there are none; the latest tested state always lives on `main`).

| UniFi Protect version | Status |
|---|---|
| **7.1.83** | ✅ **Supported** — developed and tested against this build |
| Other 7.1.x | ⚠️ **Best effort** — `apply.sh` patches only if the code anchors still match, and **aborts safely** (no file written) if they don't |
| ≤ 7.0.x and ≥ 7.2.0 | ❌ **Not supported / untested** — anchors are likely to have moved; expect a safe abort |

Because the patch is anchored to exact strings in the minified bundle, it never produces a
partially-modified file: `patch_onvif.py` asserts each of its anchors appears **exactly once**
before replacing, and `apply.sh` **syntax-checks** the result with Protect's own Node and keeps a
timestamped backup before swapping anything in. If a newer Protect build moves an anchor, the
worst case is "it refuses to apply," not a broken NVR.

## Security model

- The mod adds endpoints under Protect's existing **authenticated** third-party-camera API
  (`/proxy/protect/api/third-party-cameras/...`). They sit behind the same auth gate as the rest
  of Protect — they are not reachable unauthenticated.
- The helper page is served from Protect's own origin and uses your existing console session; it
  stores nothing and sends nothing to any third party.
- State-changing calls carry the UniFi OS `X-CSRF-Token` (captured from the `x-updated-csrf-token`
  response header).
- ONVIF credentials you enter are forwarded to Protect's adopt/probe API exactly as the stock
  onboarding flow does; the page does not persist them.

> ⚠️ This is an **unofficial modification of Ubiquiti's bundled code**. Run it only on consoles you
> own/administer, keep the backups `apply.sh` makes, and re-apply after a Protect upgrade. Use at
> your own risk; not affiliated with or endorsed by Ubiquiti.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

- Use GitHub's private reporting: **Security → Report a vulnerability** on this repository
  (Private Vulnerability Reporting), or
- Open a [GitHub Security Advisory](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/security/advisories/new).

Include the UniFi Protect version, the relevant patch anchor (R1–R11), and steps to reproduce.
Since this repo has no release cadence, accepted fixes are merged to `main` and you re-run
`apply.sh` to pick them up.
