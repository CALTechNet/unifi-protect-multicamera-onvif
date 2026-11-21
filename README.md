# UniFi Protect — ONVIF multi-camera / multi-stream picker

A small mod for **UniFi Protect** that adds a **stream/camera selection step** when you
onboard an ONVIF (third‑party) camera, instead of Protect silently auto‑picking the top
three resolutions.

After you authenticate to an ONVIF device you get a lightweight web page that:

- Lists every usable (H.264/H.265) media profile the camera exposes.
- Groups profiles by **video source**, so multi‑sensor / NVR‑style devices that present
  several physical cameras behind one IP show a **dropdown** to pick which camera.
- **1–2 streams** on a source → nothing to choose; Protect uses them as its two profiles,
  **High** + **Low**.
- **More than 2 streams** → a **checkbox list** to choose which streams to add. Of the
  streams you check, the highest‑resolution becomes **High** and the lowest becomes **Low**
  — Protect uses just **two** profiles (High and Low) for these cameras.
- Adds each selected camera. When a device exposes multiple video sources, each one you
  add becomes its own Protect device. The **first** source keeps the rig's real MAC so
  Protect's own discovery stops offering it once adopted; the extra sources get a
  per‑source synthetic MAC to stay distinct.
- Requests a per-profile snapshot for each selected source where the camera supports it.
  A reported issue with thumbnails reverting after adoption is still being investigated
  (see [#2](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/2)).
- Lets you add a stream **by URL** for a sensor the camera doesn't advertise over ONVIF —
  e.g. the telephoto lens on TP‑Link Tapo dual‑lens models (`…/stream6`).

> **Why?** Stock Protect runs auth + probe + adopt in a single request and auto‑maps the
> three highest resolutions. There is no way to choose a specific stream, and multi‑sensor
> devices behind one ONVIF endpoint can't be split into separate cameras. This mod adds a
> probe‑without‑adopt step and a selection UI on top of Protect's own API.

---

## Compatibility

| | |
|---|---|
| Console-tested | UniFi Protect **7.1.83** (Debian 11, ARM64) and **7.3.74** (Debian 13, ARM64, UDM Pro Max) |
| Offline-verified | UniFi Protect **7.3.74** (Debian 11 and 13, ARM64) |
| Node | the one Protect ships (`/usr/bin/node24`, Node 24) |
| Modifies | `/usr/share/unifi-protect/app/service.js` and installs the helper HTML under `/etc/unifi-protect/onvif-mod/` |

The patch uses exact code anchors in the minified bundle and rejects unsupported
anchors. A successful patch and syntax check **do not prove runtime compatibility**.
In particular, [Protect 7.1.87](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/16)
has a report of incorrect selected streams even though cameras can be added.

For 7.3.74, the official Debian 13 ARM64 bundle has passed an offline patch and Node 24
syntax check with RTSP-only support included. The contributor also reported a successful
live ONVIF multi-lens test on a UDM Pro Max with an AXIS P3715-PLVE. **Live RTSP-only
recording and playback have not been confirmed on a console.**
See [How it works](#how-it-works) and [`SECURITY.md`](SECURITY.md) for the supported-version policy.

> ⚠️ **This is an unofficial modification of Ubiquiti's bundled code.** A Protect upgrade
> replaces `service.js` and removes the mod — just re‑run `apply.sh`. Keep the backups the
> installer makes. Use at your own risk.

---

## Install

SSH into the console as root, then:

```bash
git clone https://github.com/CALTechNet/unifi-protect-multicamera-onvif.git
cd unifi-protect-multicamera-onvif
sudo ./apply.sh
sudo systemctl restart unifi-protect
```

`apply.sh` makes a backup and refuses to swap in a patch if the anchor checks or
JavaScript syntax check fail. **It is not idempotent:** do not run it again on an
already patched `service.js`. Start from a clean/unmodified Protect bundle before
reapplying, or restore a known-good backup first.

The script:

1. backs up the current `service.js` to `service.js.bak-onvifmod-<timestamp>`,
2. applies the patch to a copy,
3. **syntax‑checks** it with Protect's own Node before swapping it in,
4. swaps it in (it does **not** restart Protect — you do that yourself).

The restart causes a ~30–60 s interruption to live view and recording, so pick your moment.

### No `git` on the console?

The console may not have `git`. Either clone on another machine and copy the three files
(`apply.sh`, `patch_onvif.py`, `onvif_helper.html`) into one directory on the console, or
download the repo as a zip. They must sit together in the same directory.

---

## Use

1. Log into your UniFi console in a browser.
2. In the **same** browser (so it carries your session), open:

   ```
   https://<your-console>/proxy/protect/api/third-party-cameras/onvif-helper
   ```

3. Enter the camera host (`192.168.1.50` or `192.168.1.50:80`) and the ONVIF
   username / password, click **Authenticate & list streams**.
4. Pick the video source (if more than one) and tick the streams you want, then
   **Add this camera**. It appears in Protect's Devices list.
 
### Add by RTSP URL

**Add stream URL as camera** is available as soon as the helper loads, even when the
camera does not support ONVIF. Enter a High-quality RTSP URL and optionally a
Low-quality URL from the **same host**. If authentication is required, include it in
the HQ URL, for example `rtsp://user:password@192.168.1.50/stream1`. Both streams
use the same credentials; use URL encoding for special characters in passwords.

If you previously probed the same host successfully via ONVIF, the helper retains
its existing ONVIF-backed extra-lens adoption behavior. Otherwise, the RTSP-only
path skips ONVIF completely and uses a synthetic device identity based on the HQ
URL without embedded credentials. RTSP-only entries have no ONVIF PTZ or motion
event support. After installation, test both live view and playback on your Protect
console; those functions have not been verified on every firmware/camera combination.

The page only talks to Protect's own authenticated API on the same origin; it stores
nothing and sends nothing anywhere else.

---

## Uninstall / rollback

```bash
ls -t /usr/share/unifi-protect/app/service.js.bak-onvifmod-*   # newest first
sudo cp /usr/share/unifi-protect/app/service.js.bak-onvifmod-<timestamp> \
        /usr/share/unifi-protect/app/service.js
sudo systemctl restart unifi-protect
```

---

## How it works

The patch makes a handful of surgical edits to Protect's minified `service.js`. Each edit
is anchored to a unique string; `patch_onvif.py` asserts each anchor appears exactly once
before replacing, and refuses to apply twice — so it either patches cleanly or aborts.

Protect 7.3.74 uses a separate set of anchors for its updated ONVIF handlers.
When the helper adopts a specific profile, it uses Protect's manual profile
override to preserve the selected lens during periodic synchronization. It refreshes
the ONVIF profile list after adoption so profiles recently added on the camera are
available on an existing Protect device.

To check a bundle extracted from the Protect package, run

```bash
python3 patch_onvif.py --input ./service.js --output ./service.patched.js
node --check ./service.patched.js
```

| Area | Change |
|---|---|
| ONVIF profile parser (`fetchProfiles`) | carry the ONVIF `videoSourceToken` for each profile (Protect dropped it), so streams can be grouped by physical camera |
| Probe (`getCameraDetails`) | include `profileName` + `videoSourceToken` on every probed stream, and capture a **per‑profile snapshot URI** so each video source gets its own thumbnail |
| New `probe` action | authenticate and return streams grouped by video source **without** adopting (`POST /third-party-cameras/probe`) |
| Adopt subscriber | accept `profileTokens` for ONVIF stream selection, `manualStreams` for RTSP URLs, `rtspOnly` to bypass ONVIF discovery, and `macSalt` for multiple ONVIF sources; preserve selected snapshots |
| Router | accept and forward `profileTokens`, `macSalt`, `manualStreams`, and `rtspOnly`; add the `probe` route and picker page at `GET /third-party-cameras/onvif-helper` |
| ONVIF re‑sync (`syncOnvifCameraConfig` / `updateOnvifCameraInfo`) | **skip** cameras tagged as manual (`profileToken` of `manual-*`) so Protect's periodic ONVIF re‑probe doesn't overwrite a hand‑entered stream URL back to the camera's ONVIF profiles |

The picker page is served by that GET route from the same origin as Protect, so it shares
your login session — no separate web server, no CORS. At request time the route reads
`onvif_helper.html` from `/etc/unifi-protect/onvif-mod/` (installed by `apply.sh`), falling
back to a copy embedded in `service.js`. That means you can tweak the page and just refresh
the browser — **no re-patch or restart needed** for HTML/JS changes.

On UniFi OS consoles the gateway requires an `X-CSRF-Token` header on POST/PUT/DELETE. The
page handles this automatically: it captures the token from the `x-updated-csrf-token`
response header (GETs are exempt) and replays it on the `probe`/`adopt` calls, with a retry
if the gateway rotates it. Open the page from the **same console IP you log into Protect
with** so the session cookie applies.

### Files

| File | Purpose |
|---|---|
| `apply.sh` | backup → patch → syntax‑check → swap → install the page to the runtime path |
| `patch_onvif.py` | version-specific anchored edits; reads `onvif_helper.html` from its own directory |
| `onvif_helper.html` | the picker UI; installed to `/etc/unifi-protect/onvif-mod/` (read live) and embedded in `service.js` as a fallback |
| `tools/onvif_diag.py` | diagnostics: dumps a **redacted** snapshot of third‑party camera records grouped by host (for multi‑lens bug reports) — `sudo python3 tools/onvif_diag.py` |

---

## Notes & limitations

- Protect uses **two** profiles for these cameras — **High** and **Low**. Of the streams you
  check, the highest‑resolution becomes High and the lowest becomes Low; any in between are
  ignored.
- Selected streams should share one codec — Protect collapses a camera to a single codec.
- Multi‑source ("multiple cameras behind one IP") support relies on the device reporting a
  distinct ONVIF `VideoSourceConfiguration` token per sensor. Devices that don't will show
  as a single camera with all streams listed (still fully usable). For a sensor that isn't
  advertised over ONVIF at all, use **Add stream URL as camera**.
- When the helper has already probed the same host, manually added lenses keep the
  ONVIF-backed identity and fallback thumbnail. RTSP-only streams instead use a stable
  synthetic device ID derived from the HQ URL (without embedded credentials).
- Protect refines resolution from the live stream. Periodic ONVIF re-sync is disabled
  for manual streams so their URLs are not overwritten. Re-adopt after changing a URL.
- Adopting via **Add stream URL** or a non‑first video source always uses a synthetic MAC,
  so it lands as a separate Protect device and never collides with the primary.
- Manual‑stream cameras adopt with **PTZ disabled** (a raw RTSP stream has no ONVIF PTZ
  binding — leaving it on made the iOS app crash trying to drive it) and at a sane default
  frame rate / bitrate. Tick **This stream carries audio** in the picker if your RTSP URL
  includes an audio track, so Protect shows the audio controls; leave it off otherwise.
- **Dashboard live view with two devices sharing an IP:** a reporter observed a black
  tile for the second camera although **Playback → Live** worked. Adding the manual
  lens before the ONVIF lens helped in that setup, but this workaround may not apply
  to every Protect version. See [#7](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/7).
- Not affiliated with or endorsed by Ubiquiti.

---

## Known issues and troubleshooting

The items below are **not all fixed**; please do not assume that a clean patch run
means a reported runtime problem is resolved.

| Issue | Current status |
|---|---|
| [#2: Thumbnails revert after adoption](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/2) | Per-profile snapshots are requested during adoption, but a reporter observed them reverting later. Persistence remains unverified. |
| [#14: Enhanced stream compatibility resets selected profiles](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/14) | Open; stream compatibility mode may cause Protect to replace/refresh the camera record and override the selected streams. Root cause and fix are not verified. |
| [#16: Protect 7.1.87 ignores stream selection](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/16) | Open; 7.1.87 is **not verified compatible**. A patch that applies without errors does not establish that stream selection works. |
| [#7: Black Dashboard tile with multiple devices on one IP](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/7) | Reported workaround: add the manual lens before the ONVIF lens; behavior may vary across builds. |

For selection/playback problems, please provide the **exact Protect version**, console
model, camera/NVR model, whether the streams work directly in VLC, which stream
profiles you selected (token/name/resolution), and what Protect actually played
before/after the change. When safe to do so, compare the camera's settings with
`tools/onvif_diag.py`. Redact IPs, credentials, tokens, device identifiers, and
other sensitive data before posting logs or diagnostic output. Do not post RTSP
URLs containing passwords.

To **test a bundle offline without installing it**, see the `--input` / `--output`
example in [How it works](#how-it-works). Do not run an unvalidated patch directly
on a production console.

---

## How to explore the implementation

This project changes Protect's minified backend using narrowly matched string
anchors rather than replacing the entire application:

1. Start with `onvif_helper.html` for the authenticated UI and requests to
   `/third-party-cameras/probe` and `/third-party-cameras/adopt`.
2. Read `patch_onvif.py` for the version-specific changes that expose the list
   of ONVIF profiles, carry video-source tokens, select HQ/LQ streams, and assign
   distinct device identities.
3. Compare those changes with a locally extracted, unmodified Protect
   `service.js` for the **same firmware version**. The patch refuses to replace
   a string unless that anchor occurs exactly once, but this alone does not
   guarantee the new behavior is correct.
4. Use `tests/test_rtsp_only.py` and the CI workflow for reproducible offline
   checks. Live adoption and playback tests require a compatible Protect console.

Direct RTSP-only adoption works by validating the RTSP URLs, passing the stream
metadata into Protect's camera-adoption path, and deriving a stable synthetic
camera identity from the credential-free HQ URL. ONVIF is still used for ordinary
ONVIF-backed cameras. This is an unofficial integration that depends on internal
Protect code, so behavior can change with firmware updates.

---

## Security & supported versions

"Supported" here means the **UniFi Protect build** the patch is anchored to — this repo has no
release tags; the latest tested state always lives on `main`.

| UniFi Protect version | Status |
|---|---|
| **7.1.83** | ✅ Supported — developed and tested against this build |
| **7.3.74** | ONVIF multi-lens console-tested on Debian 13 ARM64; RTSP-only patching and Node syntax validated offline; live RTSP-only adoption/recording not yet verified. |
| Other 7.1.x | Not validated. **7.1.87 has a report of incorrect stream selection** ([#16](https://github.com/CALTechNet/unifi-protect-multicamera-onvif/issues/16)); anchor and syntax checks alone do not confirm behavior. |
| Other versions | Untested |

The mod adds routes behind Protect's existing **authenticated** third-party-camera API on
its own origin. The helper page does not persist credentials; Protect receives and
handles credentials as part of the camera onboarding flow. The anchored patch
can't half‑apply — `patch_onvif.py` requires each anchor exactly once and `apply.sh` syntax‑checks
the result and keeps a timestamped backup before swapping anything in.

Found a security issue? Please **don't** open a public issue — see [`SECURITY.md`](SECURITY.md)
for private reporting and the full policy.
