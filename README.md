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
| Tested on | UniFi Protect **7.1.83** (Debian 11, arm64; UNVR / UDM‑class consoles) |
| Node | the one Protect ships (`/usr/bin/node24`, Node 24) |
| Touches | only `/usr/share/unifi-protect/app/service.js` (Protect's bundled backend) |

It will likely work on nearby 7.1.x builds, but the patch matches exact code anchors in the
minified bundle — if Protect changed those functions, `apply.sh` will refuse to patch
(safe: it aborts instead of producing a broken file). See [How it works](#how-it-works) and
[`SECURITY.md`](SECURITY.md) for the supported‑version policy.

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
5. **A lens/sensor not in the list?** Some cameras expose extra sensors only over direct
   RTSP, not ONVIF (e.g. a Tapo dual‑lens camera's telephoto lens at `…/stream6` and
   `…/stream7`). Use **Add stream URL as camera** at the bottom: paste the high‑quality
   RTSP URL (and optionally a low‑quality one), and it's adopted as its own device.

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

| Area | Change |
|---|---|
| ONVIF profile parser (`fetchProfiles`) | carry the ONVIF `videoSourceToken` for each profile (Protect dropped it), so streams can be grouped by physical camera |
| Probe (`getCameraDetails`) | include `profileName` + `videoSourceToken` on every probed stream, and capture a **per‑profile snapshot URI** so each video source gets its own thumbnail |
| New `probe` action | authenticate and return streams grouped by video source **without** adopting (`POST /third-party-cameras/probe`) |
| Adopt subscriber | accept optional `profileTokens` (ordered selection) → build channels from exactly those; optional `manualStreams` build channels from caller‑supplied RTSP URLs (non‑ONVIF sensors); use the chosen source's snapshot as the thumbnail; optional `macSalt` keeps multiple sources distinct |
| Router | extend the request schema with `profileTokens` + `macSalt` + `manualStreams`; add the `probe` route and serve the picker page at `GET /third-party-cameras/onvif-helper` |

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
| `patch_onvif.py` | the 11 anchored edits; reads `onvif_helper.html` from its own directory |
| `onvif_helper.html` | the picker UI; installed to `/etc/unifi-protect/onvif-mod/` (read live) and embedded in `service.js` as a fallback |

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
- Manual stream URLs are adopted on top of an ONVIF authentication to the same host (used
  for the device name, MAC, and a fallback thumbnail), so the camera must still answer
  ONVIF on at least one lens. Protect refines the channel resolution from the live stream
  once connected.
- Adopting via **Add stream URL** or a non‑first video source always uses a synthetic MAC,
  so it lands as a separate Protect device and never collides with the primary.
- Not affiliated with or endorsed by Ubiquiti.

---

## Security & supported versions

"Supported" here means the **UniFi Protect build** the patch is anchored to — this repo has no
release tags; the latest tested state always lives on `main`.

| UniFi Protect version | Status |
|---|---|
| **7.1.83** | ✅ Supported — developed and tested against this build |
| Other 7.1.x | ⚠️ Best effort — patches only if the anchors still match, **aborts safely** otherwise |
| ≤ 7.0.x and ≥ 7.2.0 | ❌ Untested — expect a safe abort |

The mod only adds routes behind Protect's existing **authenticated** third‑party‑camera API on
its own origin; it stores no credentials and sends nothing to third parties. The anchored patch
can't half‑apply — `patch_onvif.py` requires each anchor exactly once and `apply.sh` syntax‑checks
the result and keeps a timestamped backup before swapping anything in.

Found a security issue? Please **don't** open a public issue — see [`SECURITY.md`](SECURITY.md)
for private reporting and the full policy.
