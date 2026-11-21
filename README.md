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
- Gives each adopted source **its own thumbnail** (the snapshot is fetched per video
  source, not once per device).
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
| Touches | only `/usr/share/unifi-protect/app/service.js` (Protect's bundled backend) |

The patch matches exact code anchors in the minified bundle. If an anchor differs,
`apply.sh` aborts before swapping in a new service bundle. The 7.3.74 offline check
covers patching, Node 24 syntax validation, and probe, adoption, and refresh behavior
with simulated ONVIF profiles. Live testing on 7.3.74 confirmed distinct dashboard
tiles and HQ/LQ recording playback for both sensors of an AXIS P3715-PLVE.
See [How it works](#how-it-works) and [`SECURITY.md`](SECURITY.md) for the supported-version policy.

> ⚠️ **This is an unofficial modification of Ubiquiti's bundled code.** A Protect upgrade
> replaces `service.js` and removes the mod — just re‑run `apply.sh`. Keep the backups the
> installer makes. Use at your own risk.

---

## Install

SSH into the console as root, then:

```bash
git clone https://github.com/CALTechNet/unifi-protect-multicam-onvif.git
cd unifi-protect-multicam-onvif
sudo ./apply.sh
sudo systemctl restart unifi-protect
```

`apply.sh` is idempotent and safe:

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

Use **Add stream URL as camera** for an RTSP-only camera or a lens that ONVIF doesn't
list. The URL form is available immediately, without ONVIF probing. Paste the HQ RTSP
URL and optionally an LQ URL from the same host. Include credentials in the HQ URL
if necessary (`rtsp://user:password@192.168.1.50/stream1`). Protect uses the same
credentials for both streams.

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
- **Dashboard live view with two devices on one IP:** Protect's Dashboard grid binds a
  live tile per camera IP, so when two Protect devices share one camera IP (a multi‑lens
  rig, or a manual stream added next to the ONVIF lens) only the **first‑adopted** one
  reliably shows live on the Dashboard; the second can show black even though **Playback →
  Live works for both**. Workaround: **add the helper/manual lens first, then adopt the
  native ONVIF lens.** This is Protect's own behavior, not something the patch controls.
- Not affiliated with or endorsed by Ubiquiti.

---

## Security & supported versions

"Supported" here means the **UniFi Protect build** the patch is anchored to — this repo has no
release tags; the latest tested state always lives on `main`.

| UniFi Protect version | Status |
|---|---|
| **7.1.83** | ✅ Supported — developed and tested against this build |
| **7.3.74** | ONVIF multi-lens support console-tested on Debian 13 ARM64. RTSP-only adoption requires fresh runtime verification. |
| Other 7.1.x | ⚠️ Best effort — patches only if the anchors still match, **aborts safely** otherwise |
| Other versions | Untested |

The mod only adds routes behind Protect's existing **authenticated** third‑party‑camera API on
its own origin; it stores no credentials and sends nothing to third parties. The anchored patch
can't half‑apply — `patch_onvif.py` requires each anchor exactly once and `apply.sh` syntax‑checks
the result and keeps a timestamped backup before swapping anything in.

Found a security issue? Please **don't** open a public issue — see [`SECURITY.md`](SECURITY.md)
for private reporting and the full policy.
