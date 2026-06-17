# UniFi Protect — ONVIF multi-camera / multi-stream picker

A small mod for **UniFi Protect** that adds a **stream/camera selection step** when you
onboard an ONVIF (third‑party) camera, instead of Protect silently auto‑picking the top
three resolutions.

After you authenticate to an ONVIF device you get a lightweight web page that:

- Lists every usable (H.264/H.265) media profile the camera exposes.
- Groups profiles by **video source**, so multi‑sensor / NVR‑style devices that present
  several physical cameras behind one IP show a **dropdown** to pick which camera.
- **1–2 streams** on a source → nothing to choose; Protect uses them as main + sub.
- **More than 2 streams** → a **checkbox list** to choose which streams to add. The
  highest‑resolution checked stream becomes **High**, then **Medium**, then **Low**
  (Protect uses up to three channels, but exposes only 2 to the user).
- Adds each selected camera. When a device exposes multiple video sources, each one you
  add becomes its own Protect device (kept distinct with a per‑source synthetic MAC).

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
(safe: it aborts instead of producing a broken file). See [How it works](#how-it-works).

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
| Probe (`getCameraDetails`) | include `profileName` + `videoSourceToken` on every probed stream |
| New `probe` action | authenticate and return streams grouped by video source **without** adopting (`POST /third-party-cameras/probe`) |
| Adopt subscriber | accept optional `profileTokens` (ordered selection) → build channels from exactly those; optional `macSalt` keeps multiple sources distinct |
| Router | extend the request schema with `profileTokens` + `macSalt`; add the `probe` route and serve the picker page at `GET /third-party-cameras/onvif-helper` |

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

- Protect's channel model is fixed at three (High/Medium/Low); a single source contributes
  at most three streams. Checking more than three just uses the top three by resolution.
- Selected streams should share one codec — Protect collapses a camera to a single codec.
- Multi‑source ("multiple cameras behind one IP") support relies on the device reporting a
  distinct ONVIF `VideoSourceConfiguration` token per sensor. Devices that don't will show
  as a single camera with all streams listed (still fully usable).
- Not affiliated with or endorsed by Ubiquiti.
