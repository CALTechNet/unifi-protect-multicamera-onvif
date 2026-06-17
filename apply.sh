#!/bin/bash
# Re-apply the ONVIF stream/camera picker mod to UniFi Protect's service.js.
# Safe to run after a Protect update (which replaces service.js and wipes the mod).
# Backs up, patches a copy, syntax-checks it, then swaps it in. Does NOT restart Protect.
set -euo pipefail

APP=/usr/share/unifi-protect/app
SVC="$APP/service.js"
MD="$(cd "$(dirname "$0")" && pwd)"
NODE=/usr/bin/node24
TS=$(date +%Y%m%d-%H%M%S)

[ -f "$SVC" ] || { echo "ERROR: $SVC not found"; exit 1; }
[ -x "$NODE" ] || NODE=$(readlink -f /proc/$(pgrep -f service.js | head -1)/exe)

echo "[1/5] Backing up service.js -> service.js.bak-onvifmod-$TS"
cp -p "$SVC" "$SVC.bak-onvifmod-$TS"

echo "[2/5] Applying patch -> service.js.new"
python3 "$MD/patch_onvif.py"

echo "[3/5] Syntax-checking patched bundle"
cp "$SVC.new" "/tmp/onvifmod_check_$TS.js"
"$NODE" --check "/tmp/onvifmod_check_$TS.js"
rm -f "/tmp/onvifmod_check_$TS.js"

echo "[4/5] Swapping into place"
cp -p "$SVC" "$SVC.prev-onvifmod-$TS"   # extra safety copy of what we replace
mv "$SVC.new" "$SVC"
chmod 755 "$SVC"

echo "[5/6] Installing helper page to runtime path"
RT=/etc/unifi-protect/onvif-mod/onvif_helper.html
if [ "$MD/onvif_helper.html" != "$RT" ]; then install -D -m 0644 "$MD/onvif_helper.html" "$RT"; fi

echo "[6/6] Done. service.js patched."
echo "Restart Protect to load it:   systemctl restart unifi-protect"
echo "Then open:   https://<your-nvr>/proxy/protect/api/third-party-cameras/onvif-helper"
echo "Rollback:    cp '$SVC.bak-onvifmod-$TS' '$SVC' && systemctl restart unifi-protect"
