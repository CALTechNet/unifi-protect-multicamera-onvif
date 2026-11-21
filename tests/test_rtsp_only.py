"""Focused regression checks for RTSP-only adoption and existing patch variants."""
from pathlib import Path
import importlib.util
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patch_onvif", ROOT / "patch_onvif.py")
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

assert len(patch.edits) >= 17, "7.1 patch entries lost"
assert len(patch.protect_7_3_edits()) >= 18, "7.3 patch entries lost"
assert any("RTSP-only" in label for label, _, _ in patch.edits)
assert any("RTSP-only" in label for label, _, _ in patch.protect_7_3_edits())

with tempfile.TemporaryDirectory() as folder:
    before = Path(folder) / "unsupported.js"
    after = Path(folder) / "patched.js"
    before.write_text("unsupported version", encoding="utf-8")
    run = subprocess.run(["python3", str(ROOT / "patch_onvif.py"),
                          "--input", str(before), "--output", str(after)],
                         capture_output=True, text=True)
    assert run.returncode != 0, "Unknown bundle must be rejected"
    assert not after.exists(), "Failed patch must not write an output"

js = r"""
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const vm = require('node:vm');
const payload = JSON.parse(process.argv[1]);
const sandbox = {
  r: id => id === 23957 ? { BadRequestError: Error } : crypto,
  s: { BadRequestError: Error },
  process, URL
};
const load = source => vm.runInNewContext(source + '\nreadRtspCamera;', sandbox);
const a = load(payload.a), b = load(payload.b);
const request = { manualStreams: [
  {uri:'rtsp://guest:p%40ss@10.0.0.5:554/live/high',name:'Lobby'},
  {uri:'rtsp://10.0.0.5/live/low'}
]};
for (const parse of [a,b]) {
  const result = parse(request);
  assert.equal(result.host,'10.0.0.5');
  assert.equal(result.port,'554');
  assert.equal(result.username,'guest');
  assert.equal(result.password,'p@ss');
  assert.equal(result.streams.length,2);
  assert.equal(result.streams[0].uri,'rtsp://10.0.0.5/live/high');
  assert.equal(result.name,'Lobby');
  assert.match(result.mac,/^[0-9A-F]{12}$/);
  assert.equal(parse(request).mac,result.mac,'Re-adoption keeps identity');
  assert.throws(() => parse({manualStreams:[{uri:'http://10.0.0.5/cam'}]}));
  assert.throws(() => parse({manualStreams:[{uri:'rtsp://10.0.0.5/a'}, {uri:'rtsp://10.0.0.6/b'}]}));
  assert.throws(() => parse({manualStreams:[{uri:'rtsp://u:p@10.0.0.5/a'}, {uri:'rtsp://u:wrong@10.0.0.5/b'}]}));
}
assert.equal(a(request).mac, b(request).mac, 'MAC stays stable across versions');
const htmlScript = payload.html.slice(payload.html.indexOf('<script>') + 8, payload.html.indexOf('</script>'));
new vm.Script(htmlScript);
assert.match(payload.html,/rtspOnly: !useOnvif/);
assert.match(payload.html,/cam.videoSourceToken != null/);
console.log('RTSP request validation, identities, and helper syntax: PASS');
"""
subprocess.run(["node", "-e", js, json.dumps({
    "a": patch.RTSP_CAMERA,
    "b": patch.RTSP_CAMERA_7_3,
    "html": (ROOT / "onvif_helper.html").read_text(encoding="utf-8")
})], check=True)
print("Bundle rejection and patch-variant checks: PASS")
