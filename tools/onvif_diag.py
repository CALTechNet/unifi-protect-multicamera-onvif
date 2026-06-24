#!/usr/bin/env python3
"""
onvif_diag.py — collect a redacted snapshot of UniFi Protect third-party (ONVIF)
camera records, for bug reports about the ONVIF multi-camera / multi-stream mod.

It reads Protect's camera datastore, keeps only third-party cameras, strips every
credential/secret, and groups the cameras by `host` (the camera IP). Multi-lens /
multi-source rigs — several Protect devices behind one camera IP — show up as a
group with more than one camera. That grouping is the evidence behind the
"Dashboard live view is black for the 2nd lens, but Playback->Live is fine"
report: the records share `host` while differing in `mac`/`id`, so the per-group
`shared` vs `differs` breakdown points straight at the field the live grid
collides on.

What is removed: passwords, auth tokens, key material, fingerprints, and any
user:pass@ / credential query params embedded in RTSP/snapshot URLs.
What is kept (needed to diagnose): host, mac, id, name, channels, codec,
parentCameraGroupId, connectionHost, guid, streamSharing, and the (de-credentialed)
thirdPartyCameraInfo.

Usage:
    sudo python3 onvif_diag.py                     # -> ./onvif-diag.json (+ summary on stderr)
    sudo python3 onvif_diag.py -o report.json
    sudo python3 onvif_diag.py --db /path/to/cameras.json
    sudo python3 onvif_diag.py --all               # include native (non-third-party) cams too
    sudo python3 onvif_diag.py --stdout            # print JSON instead of writing a file

Review the output before sending it; secrets are stripped, but host IPs, MACs,
and camera names remain.
"""
import argparse
import datetime
import json
import os
import re
import sys

_OID = re.compile(r"^[0-9a-fA-F]{24}$")


def oid_created(camera_id):
    """A Protect camera `id` is a Mongo ObjectId; its first 4 bytes are the
    creation (≈ adoption) time. Return an ISO string, or None if not an ObjectId.
    Lets the report show *order of adoption*, which the field reports say matters."""
    if not isinstance(camera_id, str) or not _OID.match(camera_id):
        return None
    try:
        ts = int(camera_id[:8], 16)
        return datetime.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except Exception:
        return None

DEFAULT_DB = "/etc/unifi-protect/jsonDb/cameras.json"
PKG = "/usr/share/unifi-protect/app/package.json"

# Dropped wholesale (secret / high-entropy identifiers not needed to diagnose).
SECRET_CAMERA_KEYS = {
    "password", "authToken", "naclKeyPair", "fingerprint", "fingerprintSettings",
    "anonymousDeviceId", "homekitAccessoryId", "homekitSettings",
}
SECRET_TP_KEYS = {"password"}
URL_TP_KEYS = ("rtspUrl", "rtspUrlLQ", "snapshotUrl", "mediaUri")

# Curated top-level fields kept per camera (others dropped to cut noise). Missing
# keys are simply skipped.
CAMERA_FIELDS = [
    "id", "name", "type", "mac", "host", "connectionHost", "guid",
    "isThirdPartyCamera", "isAdopted", "isProvisioned", "isAdopting",
    "state", "videoCodec", "videoCodecState", "videoMode", "videoInputMode",
    "rtspClient", "parentCameraGroupId", "elementInfo", "ptz", "ptzControlEnabled",
    "streamSharing", "lastSeen", "lastDisconnect", "channels", "thirdPartyCameraInfo",
]
CHANNEL_FIELDS = [
    "id", "videoId", "name", "enabled", "isRtspEnabled", "rtspAlias",
    "isInternalRtspEnabled", "internalRtspAlias", "width", "height", "fps",
    "bitrate", "idrInterval",
]
# Scalar fields compared across cameras in a host group (shared vs differs).
COMPARE_FIELDS = [
    "name", "mac", "host", "connectionHost", "guid", "type", "videoCodec",
    "parentCameraGroupId", "elementInfo", "rtspClient", "ptz",
    "isThirdPartyCamera", "isAdopted", "isProvisioned",
]


def redact_url(u):
    """Strip user:pass@ and credential query params from a URL-ish string."""
    if not isinstance(u, str):
        return u
    u = re.sub(r"//[^/@]*@", "//<creds>@", u)
    u = re.sub(r"(?i)\b(user(?:name)?|pass(?:word)?|token|auth)=[^&\s]*", r"\1=<redacted>", u)
    return u


def pick(d, fields):
    return {k: d[k] for k in fields if k in d}


def curate_camera(c):
    out = pick(c, CAMERA_FIELDS)
    for k in SECRET_CAMERA_KEYS:
        out.pop(k, None)
    if isinstance(out.get("channels"), list):
        out["channels"] = [pick(ch, CHANNEL_FIELDS) for ch in out["channels"]]
    tp = out.get("thirdPartyCameraInfo")
    if isinstance(tp, dict):
        tp = dict(tp)
        for k in SECRET_TP_KEYS:
            tp.pop(k, None)
        for k in URL_TP_KEYS:
            if k in tp:
                tp[k] = redact_url(tp[k])
        out["thirdPartyCameraInfo"] = tp
    return out


def compare_group(cams):
    """Return (shared, differs) over COMPARE_FIELDS for cameras sharing a host."""
    shared, differs = {}, {}
    for f in COMPARE_FIELDS:
        present = [c for c in cams if f in c]
        if not present:
            continue
        vals = [c.get(f) for c in present]
        if all(json.dumps(v, sort_keys=True) == json.dumps(vals[0], sort_keys=True) for v in vals):
            shared[f] = vals[0]
        else:
            differs[f] = {c.get("id", "?"): c.get(f) for c in present}
    return shared, differs


def protect_version():
    try:
        return json.load(open(PKG)).get("version")
    except Exception:
        return None


def load_cameras(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("cameras", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        # last resort: first list value
        for v in data.values():
            if isinstance(v, list):
                return v
    raise SystemExit(f"Unrecognized datastore shape in {path}")


def main():
    ap = argparse.ArgumentParser(description="Collect redacted ONVIF camera records for a bug report.")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"path to cameras.json (default {DEFAULT_DB})")
    ap.add_argument("-o", "--out", default="onvif-diag.json", help="output file (default onvif-diag.json)")
    ap.add_argument("--all", action="store_true", help="include native (non-third-party) cameras too")
    ap.add_argument("--stdout", action="store_true", help="print JSON to stdout instead of writing a file")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"ERROR: {args.db} not found. Pass --db <path to cameras.json>.")

    cams = load_cameras(args.db)
    selected = [c for c in cams if args.all or c.get("isThirdPartyCamera")]
    curated = [curate_camera(c) for c in selected]

    groups = {}
    for c in curated:
        groups.setdefault(c.get("host", "<no-host>"), []).append(c)

    # Tag each camera with its approximate adoption time (from the ObjectId).
    for c in curated:
        c["adoptedApprox"] = oid_created(c.get("id"))

    host_groups = []
    for host, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
        shared, differs = compare_group(members)
        ordered = sorted(members, key=lambda c: (c.get("adoptedApprox") or "", c.get("id") or ""))
        host_groups.append({
            "host": host,
            "cameraCount": len(members),
            "multiCamera": len(members) > 1,
            # Order adopted on this host — the report says the 2nd-adopted lens is
            # the one whose Dashboard live view goes black.
            "adoptionOrder": [
                {"id": c.get("id"), "name": c.get("name"), "adoptedApprox": c.get("adoptedApprox")}
                for c in ordered
            ],
            "shared": shared,
            "differs": differs,
            "cameras": members,
        })

    report = {
        "generatedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "protectVersion": protect_version(),
        "dbPath": os.path.abspath(args.db),
        "totalCameras": len(cams),
        "selectedCameras": len(selected),
        "includesNativeCameras": bool(args.all),
        "multiCameraHosts": [g["host"] for g in host_groups if g["multiCamera"]],
        "hostGroups": host_groups,
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.stdout:
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")

    multi = report["multiCameraHosts"]
    print(f"[onvif_diag] Protect {report['protectVersion']} — "
          f"{report['selectedCameras']} camera(s) in scope, "
          f"{len(host_groups)} host group(s).", file=sys.stderr)
    if multi:
        print(f"[onvif_diag] Multi-camera host(s) (the multi-lens case): {', '.join(map(str, multi))}",
              file=sys.stderr)
    else:
        print("[onvif_diag] No host has >1 camera — nothing for the dashboard-live bug to collide on here.",
              file=sys.stderr)
    if not args.stdout:
        print(f"[onvif_diag] Wrote {os.path.abspath(args.out)} — review it, then send it to the maintainer.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
