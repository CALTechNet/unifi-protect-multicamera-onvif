#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

edits = []  # 7.1.x (label, old, new)
SALTED_MAC = r'''(()=>{const z=String(e)+"|"+String(t.macSalt);let q=2166136261;for(let i=0;i<z.length;i++){q=(q^z.charCodeAt(i))>>>0,q=Math.imul(q,16777619)>>>0}let w=1540483477;for(let i=z.length-1;i>=0;i--){w=(w^z.charCodeAt(i))>>>0,w=Math.imul(w,16777619)>>>0}const b=[q>>>24&255,q>>>16&255,q>>>8&255,q&255,w>>>8&255,w&255];return b[0]=b[0]&254|2,b.map(x=>x.toString(16).padStart(2,"0")).join("").toUpperCase()})()'''

# R1: media2 profile parser -> carry videoSourceToken
edits.append((
 "R1 fetchProfiles media2 videoSourceToken",
 r'''audioEncoderConfiguration:(null===(i=e.Configurations)||void 0===i?void 0:i.AudioEncoder)?O(e.Configurations.AudioEncoder):void 0}})''',
 r'''audioEncoderConfiguration:(null===(i=e.Configurations)||void 0===i?void 0:i.AudioEncoder)?O(e.Configurations.AudioEncoder):void 0,videoSourceToken:e.Configurations?.VideoSource?.SourceToken??e.Configurations?.VideoSource?.["@_token"]}})''',
))

# R2: media1 profile parser -> carry videoSourceToken
edits.append((
 "R2 fetchProfiles media1 videoSourceToken",
 r'''e.AudioEncoderConfiguration?O(e.AudioEncoderConfiguration):void 0}})''',
 r'''e.AudioEncoderConfiguration?O(e.AudioEncoderConfiguration):void 0,videoSourceToken:e.VideoSourceConfiguration?.SourceToken??e.VideoSourceConfiguration?.["@_token"]}})''',
))

# R3: getCameraDetails -> include profileName + videoSourceToken on each stream,
#     and capture a PER-PROFILE snapshot URI so each video source gets its own
#     thumbnail instead of every camera reusing the device-level snapshot (issue #2).
edits.append((
 "R3 getCameraDetails stream fields + per-profile snapshot",
 r'''const o=(0,a.replaceUrlHostname)(await(0,n.getStreamUri)(u,t.token),e);g.push({resolution:r.resolution,encoding:r.encoding,quality:r.quality,bitrate:r.rateControl.bitrateLimit,fps:r.rateControl.frameRateLimit,uri:o,hasAudio:i,profileToken:t.token})''',
 r'''const o=(0,a.replaceUrlHostname)(await(0,n.getStreamUri)(u,t.token),e);let __snap;try{__snap=(0,a.replaceUrlHostname)(await(0,n.getSnapshotUri)(u,t.token),e)}catch(__e){__snap=void 0}g.push({resolution:r.resolution,encoding:r.encoding,quality:r.quality,bitrate:r.rateControl.bitrateLimit,fps:r.rateControl.frameRateLimit,uri:o,hasAudio:i,profileToken:t.token,profileName:t.name,videoSourceToken:t.videoSourceToken,snapshotUri:__snap})''',
))

RTSP_CAMERA = r'''
function readRtspCamera(request) {
    const { BadRequestError } = r(23957);
    const streams = request.manualStreams;
    if ("camera" in request || !streams || streams.length < 1 || streams.length > 2) {
        throw new BadRequestError("Supply one high-quality RTSP URL and optionally one low-quality URL.");
    }
    let urls, credentials;
    try {
        urls = streams.map(({ uri }) => {
            const url = new URL(uri);
            if (!/^rtsps?:\/\//i.test(uri) || !url.hostname) throw new Error();
            return url;
        });
        credentials = urls.map(url => [decodeURIComponent(url.username), decodeURIComponent(url.password)]);
    } catch {
        throw new BadRequestError("Use a valid rtsp:// or rtsps:// URL for each stream.");
    }
    const high = urls[0];
    const host = high.hostname.toLowerCase();
    const [username, password] = credentials[0];
    if (urls[1] && urls[1].hostname.toLowerCase() !== host) {
        throw new BadRequestError("The high- and low-quality RTSP streams must use the same host.");
    }
    const [lowUser, lowPass] = credentials[1] || [];
    if ((lowUser || lowPass) && (lowUser !== username || lowPass !== password)) {
        throw new BadRequestError("Use the same credentials for both RTSP streams.");
    }
    const defaultPort = high.protocol === "rtsps:" ? "322" : "554";
    const port = high.port || defaultPort;
    const cleanStreams = urls.map((url, index) => {
        url.username = url.password = url.hash = "";
        return { ...streams[index], uri: url.href };
    });
    high.hostname = host;
    if (high.port === defaultPort) high.port = "";
    const id = r(76982).createHash("sha256").update("rtsp-only|" + high.href).digest().subarray(0, 6);
    id[0] = (id[0] & 254) | 2;
    return { host, port, username, password, streams: cleanStreams,
        name: streams[0].name?.trim() || host, mac: id.toString("hex").toUpperCase() };
}
'''


# Preserve the 7.1 synthetic identity on 7.3 with Node 24 built-in crypto.
RTSP_CAMERA_7_3 = (RTSP_CAMERA
    .replace("const { BadRequestError } = r(23957);", "const BadRequestError = s.BadRequestError;")
    .replace('r(76982).createHash("sha256")',
             'process.getBuiltinModule("node:crypto").createHash("sha256")'))

# R4: adopt subscriber -> (a) honor selected profileTokens before building channels;
#     (b) optionally build channels from caller-supplied manual RTSP URLs for streams
#         the camera doesn't expose over ONVIF, e.g. a Tapo telephoto lens (issue #3);
#     (c) use the chosen source's per-profile snapshot URI as the thumbnail (issue #2).
edits.append((
 "R4 adopt stream selection + manual streams + per-source snapshot",
 r'''const{streams:E,hqStream:_,lqStream:T,encoding:A}=(0,p.getStreamData)(S),R=S.snapshotUri;''',
 r'''const __man=__rtsp?__rtsp.streams:Array.isArray(t.manualStreams)?t.manualStreams.filter(m=>m&&m.uri):[],__sel=!__rtsp&&Array.isArray(t.profileTokens)&&t.profileTokens.length>0?t.profileTokens:null,__Sx=__sel?{...S,streams:S.streams.filter(x=>__sel.includes(x.profileToken)).sort((a,b)=>__sel.indexOf(a.profileToken)-__sel.indexOf(b.profileToken))}:S,__Sf=__man.length>0?{...S,ptz:!1,streams:__man.map((m,i)=>({resolution:{width:Number(m.width)||(0===i?1920:640),height:Number(m.height)||(0===i?1080:480)},encoding:m.encoding||"h264",quality:"",bitrate:Number(m.bitrate)>0?Number(m.bitrate):(0===i?2048:512),fps:Number(m.fps)>0?Number(m.fps):30,uri:m.uri,hasAudio:!!m.hasAudio,profileToken:(__rtsp?"manual-rtsp-":"manual-")+i,profileName:m.name||"Manual stream "+(i+1),videoSourceToken:t.macSalt||"manual",snapshotUri:void 0}))}:__sel&&__Sx.streams.length>0?__Sx:S;const{streams:E,hqStream:_,lqStream:T,encoding:A}=(0,p.getStreamData)(__Sf),R=_&&_.snapshotUri||S.snapshotUri;''',
))

# R14: build the camera settings from the (manual-aware) __Sf instead of S, so manual
#   streams adopt with PTZ disabled. A raw RTSP stream has no ONVIF PTZ binding, but the
#   manual camera was inheriting ptzControlEnabled from the wide-lens probe (S.ptz=true);
#   the iOS/web app then fires /ptz/home + /enable-control, times out, and crashes. __Sf
#   carries ptz:false for manual adopts and S's own ptz otherwise. (issue #10)
edits.append((
 "R14 adopt camera settings from __Sf (ptz off for manual)",
 r'''return await h.updateAndSave({host:v,...(0,m.getOnvifDefaultCameraSettings)(e.store,S,E)''',
 r'''const settings=(0,m.getOnvifDefaultCameraSettings)(e.store,__Sf,E);
 if(__rtsp){
     settings.featureFlags.hasMotionDetection=false;
     settings.recordingSettings.enableMotionDetection=false;
 }
 return await h.updateAndSave({host:v,...settings''',
))

# R5: adopt subscriber -> optional per-source MAC salt so multiple cameras behind one endpoint stay distinct
edits.append((
 "R5 adopt mac salt",
 r'''const e=await(0,u.getMAC)(v,S);n.default.ok(e,"Failed to get MAC address"),h=null!==(r=o.findByMac("camera",e))&&void 0!==r?r:o.createRecord("camera",{mac:e})''',
 r'''let e=__rtsp?__rtsp.mac:await(0,u.getMAC)(v,S);n.default.ok(e,"Failed to get MAC address"),!__rtsp&&t.macSalt&&(e='''
 + SALTED_MAC + r'''),h=null!==(r=o.findByMac("camera",e))&&void 0!==r?r:o.createRecord("camera",{mac:e})''',
))

# R6: register the probe subscriber in the event map
edits.append((
 "R6 subscriber map probe",
 r'''"thirdPartyCameras.adopt":d.adopt,''',
 r'''"thirdPartyCameras.adopt":d.adopt,"thirdPartyCameras.probe":d.probe,''',
))

# R7: adopt module -> add probe() export (auth + list streams grouped by video source, no adoption)
edits.append((
 "R7 adopt module add probe()",
 r'''t.adopt=async(e,t)=>{var r;const{store:o}=e,{username:c,password:g}=t;try{let h,v,y;''',
 r'''t.probe=async(e,t)=>{const{username:c,password:g}=t;let v,y;if("camera"in t){const h=t.camera;v=h.host,y=h.thirdPartyCameraInfo.port}else{if(!("host"in t))throw new Error("Invalid probe parameters");[v,y="80"]=t.host.split(":")}n.default.ok(v,"Missing camera host"),n.default.ok(y,"Missing camera port");const S=await(0,l.getCameraDetails)(v,y.toString(),c,g,{});if(!S.success)throw new s.UnauthorizedError({details:S.errors});const G=new Map;for(const st of S.streams){const en=(st.encoding||"").toLowerCase();if(!en.includes("264")&&!en.includes("265"))continue;const k=st.videoSourceToken||"__default__";G.has(k)||G.set(k,[]),G.get(k).push({profileToken:st.profileToken,profileName:st.profileName||st.profileToken,encoding:st.encoding,width:st.resolution?st.resolution.width:0,height:st.resolution?st.resolution.height:0,fps:st.fps,bitrate:st.bitrate,hasAudio:!!st.hasAudio})}const cams=Array.from(G.entries()).map(([k,arr],idx)=>(arr.sort((a,b)=>b.width-a.width),{videoSourceToken:"__default__"===k?null:k,label:"__default__"===k?S.name||"Camera "+(idx+1):(S.name||"Camera")+" #"+(idx+1),streams:arr}));return{name:S.name,ptz:!!S.ptz,success:!0,errors:S.errors,host:v,port:String(y),cameras:cams}};t.adopt=async(e,t)=>{var r;const{store:o}=e,{username:c,password:g}=t;try{let h,v,y;''',
))

# R15: validate RTSP-only requests and skip ONVIF details and credentials.
edits.append((
 "R15 adopt RTSP-only streams without ONVIF",
 r'''t.adopt=async(e,t)=>{var r;const{store:o}=e,{username:c,password:g}=t;try{let h,v,y;if("camera"in t)h=t.camera,v=h.host,y=h.thirdPartyCameraInfo.port;else{if(!("host"in t))throw new Error("Invalid adoption parameters");[v,y="80"]=t.host.split(":")}n.default.ok(v,"Missing camera host"),n.default.ok(y,"Missing camera port");const S=await(0,l.getCameraDetails)(v,y.toString(),c,g,{fetchHwAddress:!0});if(f.info(`Adopting camera at ${v}:${y} with details`,S),!S.success)throw new s.UnauthorizedError({details:S.errors});''',
 RTSP_CAMERA + r'''t.adopt=async(e,t)=>{var r;const{store:o}=e;let{username:c,password:g}=t;const __rtsp=t.rtspOnly?readRtspCamera(t):null;
 try{let h,v,y,S;
 if(__rtsp){
     ({host:v,port:y,username:c,password:g}=__rtsp);
     S={success:true,name:__rtsp.name,ptz:false,errors:[]};
 }else{
     if("camera"in t)h=t.camera,v=h.host,y=h.thirdPartyCameraInfo.port;else{if(!("host"in t))throw new Error("Invalid adoption parameters");[v,y="80"]=t.host.split(":")}
     n.default.ok(v,"Missing camera host"),n.default.ok(y,"Missing camera port");
     S=await(0,l.getCameraDetails)(v,y.toString(),c,g,{fetchHwAddress:!0});
     if(f.info(`Adopting camera at ${v}:${y} with details`,S),!S.success)throw new s.UnauthorizedError({details:S.errors});
 }''',
))

# R8: extend adopt/probe request schema to allow profileTokens + macSalt + manualStreams
edits.append((
 "R8 router schema profileTokens/macSalt/manualStreams",
 r'''.and(i.z.object({username:i.z.string(),password:i.z.string()}))''',
 r'''.and(i.z.object({username:i.z.string(),password:i.z.string(),profileTokens:i.z.array(i.z.string()).optional(),macSalt:i.z.string().optional(),rtspOnly:i.z.boolean().optional(),manualStreams:i.z.array(i.z.object({uri:i.z.string(),quality:i.z.string().optional(),name:i.z.string().optional(),encoding:i.z.string().optional(),width:i.z.number().optional(),height:i.z.number().optional(),hasAudio:i.z.boolean().optional(),fps:i.z.number().optional(),bitrate:i.z.number().optional()})).optional()}))''',
))

# R9: thread selection through adopt route (camera branch)
edits.append((
 "R9 router adopt n camera branch",
 r'''n={camera:t,username:i,password:a,user:e.user}''',
 r'''n={camera:t,username:i,password:a,user:e.user,profileTokens:e.body.profileTokens,macSalt:e.body.macSalt,rtspOnly:e.body.rtspOnly,manualStreams:e.body.manualStreams}''',
))

# R10: thread selection through adopt route (host branch)
edits.append((
 "R10 router adopt n host branch",
 r'''else n={host:o,username:i,password:a,user:e.user}''',
 r'''else n={host:o,username:i,password:a,user:e.user,profileTokens:e.body.profileTokens,macSalt:e.body.macSalt,rtspOnly:e.body.rtspOnly,manualStreams:e.body.manualStreams}''',
))

# R12: don't let Protect's periodic ONVIF re-sync overwrite a manually-added stream.
#   syncOnvifCameraConfig() re-probes the camera over ONVIF and rewrites rtspUrl/
#   rtspUrlLQ/channels from the discovered profiles. For a camera added via the
#   helper's stream-URL path that is *also* ONVIF-reachable (e.g. a Tapo dual-lens:
#   wide over ONVIF, telephoto by URL), this clobbers the hand-entered stream6/stream7
#   back to the wide-lens stream1/stream2. Manual cameras are tagged with a
#   profileToken of "manual-*" (see R4); bail out for them so the URL sticks. (issue #7)
edits.append((
 "R12 skip ONVIF config sync for manual streams",
 r'''t.syncOnvifCameraConfig=async(e,t,r)=>{var i,d,l,u,p,m,f,g,h,v,y,S,E,_;if(!r.success)return;''',
 r'''t.syncOnvifCameraConfig=async(e,t,r)=>{var i,d,l,u,p,m,f,g,h,v,y,S,E,_;if(!r.success)return;if(t.thirdPartyCameraInfo&&"string"==typeof t.thirdPartyCameraInfo.profileToken&&0===t.thirdPartyCameraInfo.profileToken.indexOf("manual"))return;''',
))

# R13: same guard for updateOnvifCameraInfo (re-probes ONVIF to refresh hasAudio/
#   errors/featureFlags) — skip it for manual-stream cameras so they aren't probed
#   against the wrong lens. (issue #7)
edits.append((
 "R13 skip ONVIF info refresh for manual streams",
 r'''t.updateOnvifCameraInfo=async(e,t)=>{i.default.ok(e.host,"Camera host is not defined")''',
 r'''t.updateOnvifCameraInfo=async(e,t)=>{if(e.thirdPartyCameraInfo&&"string"==typeof e.thirdPartyCameraInfo.profileToken&&0===e.thirdPartyCameraInfo.profileToken.indexOf("manual"))return;i.default.ok(e.host,"Camera host is not defined")''',
))

# R16: RTSP-only cameras have no ONVIF event service.
edits.append((
 "R16 skip motion event subscription for RTSP-only cameras",
 r'''if(!r||!r.isThirdPartyCamera||!r.mac)return;const n=r.mac;if(!r.recordingSettings.enableMotionDetection)''',
 r'''if(!r||!r.isThirdPartyCamera||!r.mac||r.thirdPartyCameraInfo.profileToken?.startsWith("manual-rtsp-"))return;const n=r.mac;if(!r.recordingSettings.enableMotionDetection)''',
))

# R17: Keep the existing stream-based health check. An ONVIF probe can't tell
# whether an RTSP-only camera is reachable when its stream is down.
edits.append((
 "R17 skip ONVIF health fallback for RTSP-only cameras",
 r'''continue}const t=r.host;if(!t){c.warn(`Third party camera ${r.logId} has no host, can't run health check, skipping`);''',
 r'''continue}if(r.thirdPartyCameraInfo.profileToken?.startsWith("manual-rtsp-"))continue;const t=r.host;if(!t){c.warn(`Third party camera ${r.logId} has no host, can't run health check, skipping`);''',
))

# ---- R11: add /probe route, the helper HTML, and the /onvif-helper GET route ----
PROBE_ROUTE = r'''E.route({method:g.MethodNames.POST,path:"/third-party-cameras/probe",description:"Probe an ONVIF camera for available streams without adopting",summary:"Probe ONVIF streams",tags:_,schema:{requestBody:{content:{[f.ContentTypes.JSON]:{schema:T}}},responses:(0,p.defaultJsonResponse)({[h.StatusCodes.OK]:{description:"Probe result"},[h.StatusCodes.BAD_REQUEST]:{description:"Unsupported camera"}})},handlers:[(0,S.validateUserPermission)(s.AccessMode.CREATE,"camera"),(0,y.validateGranularUserPermission)(c.GranularAccess.SETTINGS_EDIT,s.AccessMode.CREATE,n.NvrDecalModel.modelKey,a.CameraDecalModel.modelKey),(0,u.createPayloadValidator)("body",T),async function(e,t){const{id:r,host:o,username:i,password:a}=e.body;let m;if(r){const t=this.store.findByPk("camera",e.body.id);if(!t)throw new l.NotFoundError({info:{entity:"camera",id:e.body.id}});m={camera:t,username:i,password:a,user:e.user}}else m={host:o,username:i,password:a,user:e.user};const P=await(0,d.publish)("thirdPartyCameras.probe",m);P?t.json(P):t.status(400).end()}]});'''

HELPER_ROUTE = r'''E.route({method:g.MethodNames.GET,path:"/third-party-cameras/onvif-helper",description:"ONVIF onboarding helper UI",summary:"ONVIF onboarding helper UI",tags:_,schema:{responses:(0,p.defaultJsonResponse)({[h.StatusCodes.OK]:{description:"HTML page"}})},handlers:[async function(e,t){let h;try{h=r(79896).readFileSync("/etc/unifi-protect/onvif-mod/onvif_helper.html","utf8")}catch(_){h=__onvifHelperHtml}t.setHeader("Content-Type","text/html; charset=utf-8"),t.status(200).end(h)}]});'''

HTML = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "onvif_helper.html"), "r", encoding="utf-8").read()

R11_old = r'''t.status(200).end()}]}),t.thirdPartyCamerasRouter=E}'''
R11_new = (r'''t.status(200).end()}]});'''
           + PROBE_ROUTE
           + "const __onvifHelperHtml=" + json.dumps(HTML) + ";"
           + HELPER_ROUTE
           + r'''t.thirdPartyCamerasRouter=E}''')
edits.append(("R11 router probe+helper routes", R11_old, R11_new))

ADOPT_7_3 = 't.adopt=async(e,t)=>{const{store:r}=e,{username:o,password:d}=t;try{let A,I,R;'


def protect_7_3_edits():
    changes = []

    def replace(label, old, new):
        changes.append((label, old, new))

    # Media2 returns only the configuration types named in GetProfiles.
    replace("7.3 request Media2 video source",
            'Type:["VideoEncoder","AudioEncoder"]', 'Type:["VideoEncoder","AudioEncoder","VideoSource"]')
    media2_audio = 'audioEncoderConfiguration:(null===(i=e.Configurations)||void 0===i?void 0:i.AudioEncoder)?P(e.Configurations.AudioEncoder):void 0'
    replace("7.3 Media2 video source", media2_audio + '}},t,r)',
            media2_audio + ',videoSourceToken:e.Configurations?.VideoSource?.SourceToken??e.Configurations?.VideoSource?.["@_token"]}},t,r)')
    media1_audio = 'audioEncoderConfiguration:e.AudioEncoderConfiguration?P(e.AudioEncoderConfiguration):void 0'
    replace("7.3 Media1 video source", media1_audio + '}},t,r)',
            media1_audio + ',videoSourceToken:e.VideoSourceConfiguration?.SourceToken??e.VideoSourceConfiguration?.["@_token"]}},t,r)')

    stream_uri = 'const o=(0,a.replaceUrlHostname)(await(0,s.getStreamUri)(m,r.token),e);'
    stream = 'v.push({resolution:i.resolution,encoding:i.encoding,quality:i.quality,bitrate:(0,t.normalizeBitrate)(i.rateControl.bitrateLimit),fps:i.rateControl.frameRateLimit,uri:o,hasAudio:n,profileToken:r.token})'
    snapshot = '''let __snapshot;
        if (u?.snapshotProfileTokens?.includes(r.token)) {
          try { __snapshot = (0,a.replaceUrlHostname)(await (0,s.getSnapshotUri)(m,r.token),e); }
          catch { /* Fall back to the camera's default snapshot. */ }
        }
        '''
    replace("7.3 stream profile and snapshot", stream_uri + stream,
            stream_uri + snapshot + stream[:-2] + ',profileName:r.name,videoSourceToken:r.videoSourceToken,snapshotUri:__snapshot})')

    # Keep separate helpers inside the existing ONVIF subscriber module.
    probe = '''const __publishOnvif = r(376995).publish;
    const __seedAdoptedProfiles = async (camera, selected) => {
      if (selected && camera.mac) {
        await __publishOnvif("onvif.clearConnection", camera.mac).catch(error => {
          T.debug(`Failed to clear the ONVIF connection for ${camera.logId}`, error);
        });
      }
      return (0,_.seedAvailableProfiles)(camera,{overwriteExisting:!0});
    };
    t.probe = async (e, request) => {
      const {username, password, camera, host} = request;
      const [hostname, port = "80"] = camera
        ? [camera.host, camera.thirdPartyCameraInfo.port]
        : host.split(":");
      n.default.ok(hostname, "Missing camera host");
      n.default.ok(port, "Missing camera port");
      const details = await (0,p.getCameraDetails)(hostname, String(port), username, password, {});
      if (!details.success) throw new s.UnauthorizedError({details:details.errors});
      const groups = new Map();
      for (const stream of details.streams) {
        if (!/26[45]/.test(stream.encoding)) continue;
        const rawSource = stream.videoSourceToken;
        const source = rawSource == null || rawSource === "" ? null : String(rawSource);
        if (!groups.has(source)) groups.set(source, []);
        groups.get(source).push({
          profileToken:stream.profileToken, profileName:stream.profileName || stream.profileToken,
          encoding:stream.encoding, width:stream.resolution.width, height:stream.resolution.height,
          fps:stream.fps, bitrate:stream.bitrate, hasAudio:!!stream.hasAudio
        });
      }
      const cameras = Array.from(groups, ([videoSourceToken, streams], index) => ({
        videoSourceToken,
        label:videoSourceToken ? details.name + " #" + (index+1) : details.name,
        streams:streams.sort((first, second) => second.width-first.width)
      }));
      return {name:details.name, ptz:!!details.ptz, success:true, errors:details.errors,
        host:hostname, port:String(port), cameras};
    };
    '''
    replace("7.3 probe subscriber", ADOPT_7_3, probe + RTSP_CAMERA_7_3 + ADOPT_7_3.replace(
        'const{store:r}=e,{username:o,password:d}=t;try',
        'const{store:r}=e;let{username:o,password:d}=t;const __rtsp=t.rtspOnly?readRtspCamera(t):null;try'))
    subscriber = '"thirdPartyCameras.adopt":d.adopt,'
    replace("7.3 subscriber registry", subscriber, subscriber + '"thirdPartyCameras.probe":d.probe,')

    # Reuse the 7.1 hash so virtual MAC addresses survive Protect updates.
    selection = '''const __sourceStreams=__rtsp?.streams??t.manualStreams;
    const __manual = __sourceStreams?.length > 0;
    const __selected = !__rtsp && t.profileTokens?.length > 0;
    const __override = __manual || __selected;
    const __details = __manual ? {...C, ptz:false, streams:__sourceStreams.map((stream,index) => ({
      resolution:{width:stream.width || (index ? 640 : 1920), height:stream.height || (index ? 480 : 1080)},
      encoding:stream.encoding || "h264", quality:"", bitrate:stream.bitrate > 0 ? stream.bitrate : (index ? 512 : 2048),
      fps:stream.fps > 0 ? stream.fps : 30, uri:stream.uri, hasAudio:!!stream.hasAudio,
      profileToken:(__rtsp?"manual-rtsp-":"manual-") + index
    }))} : __selected ? {...C, streams:C.streams.filter(stream => t.profileTokens.includes(stream.profileToken))} : C;
    const b=(0,h.getStreamData)(__details);'''
    replace("7.3 probe selected profile snapshots", 'o,d,{fetchHwAddress:!0});if(T.info(`Adopting camera at',
            'o,d,{fetchHwAddress:!0,snapshotProfileTokens:t.profileTokens});if(T.info(`Adopting camera at')
    replace("7.3 selected streams", 'const b=(0,h.getStreamData)(C);', selection)
    replace("7.3 RTSP-only bypass ONVIF connection",
            'const C=await(0,p.getCameraDetails)(I,R.toString(),o,d,{fetchHwAddress:!0,snapshotProfileTokens:t.profileTokens});',
            'if(__rtsp){I=__rtsp.host;R=__rtsp.port;o=__rtsp.username;d=__rtsp.password}'
            'const C=__rtsp?{success:true,name:__rtsp.name,ptz:false,errors:[],streams:__rtsp.streams}:'
            'await(0,p.getCameraDetails)(I,R.toString(),o,d,{fetchHwAddress:!0,snapshotProfileTokens:t.profileTokens});')
    identity = '''N=__manual ? null : M.snapshotUri ?? C.snapshotUri;
      const P=__rtsp?__rtsp.mac:await (0,g.getMAC)(I,C);
      const __mac = !__rtsp && P && t.macSalt ? (e => ''' + SALTED_MAC + ''')(P) : P;
      A=await (0,v.onvifResolveAdoptionCamera)(r,t.macSalt || __rtsp ? void 0 : A,__mac,T),'''
    replace("7.3 source snapshot and identity",
            'N=C.snapshotUri,P=await(0,g.getMAC)(I,C);A=await(0,v.onvifResolveAdoptionCamera)(r,A,P,T),',
            identity)
    replace("7.3 selected camera settings", '(0,y.getOnvifDefaultCameraSettings)(e.store,C,O,k,F)',
            '((settings)=>{if(__rtsp){settings.featureFlags.hasMotionDetection=false;'
            'settings.recordingSettings.enableMotionDetection=false}return settings})'
            '((0,y.getOnvifDefaultCameraSettings)(e.store,__details,O,k,F))')
    camera_info = 'rtspUrlLQ:null==D?void 0:D.uri,profileTokenLQ:null==D?void 0:D.profileToken,snapshotUrl:N'
    replace("7.3 persist selected profile override", camera_info,
            'rtspUrlLQ:D?.uri??(__override?null:void 0),profileTokenLQ:D?.profileToken??(__override?null:void 0),'
            'snapshotUrl:N,...__override?{manualProfileOverride:!0,hasAudio:!!M.hasAudio}:{}')
    replace("7.3 refresh profile capabilities after selected adoption",
            '(0,_.seedAvailableProfiles)(A,{overwriteExisting:!0}).catch',
            '(__rtsp?Promise.resolve():__seedAdoptedProfiles(A,__selected)).catch')

    sync_prologue = 't.syncOnvifCameraConfig=async(e,t,r)=>{var a,f,h,v;if(!r.success)return;'
    replace("7.3 preserve manual RTSP URLs during sync", sync_prologue,
            sync_prologue + 'if(t.thirdPartyCameraInfo.profileToken?.startsWith("manual-"))return;')
    replace("7.3 preserve selected profile snapshot during sync", 'let R=!1;(null!==(a=r.snapshotUri)',
            'let R=!1;(!S.manualProfileOverride||!S.snapshotUrl)&&(null!==(a=r.snapshotUri)')
    refresh = 't.updateOnvifCameraInfo=async(e,t)=>{i.default.ok(e.host,"Camera host is not defined")'
    replace("7.3 preserve manual RTSP camera info", refresh,
            refresh.replace('{i.default', '{if(e.thirdPartyCameraInfo.profileToken?.startsWith("manual-"))return;i.default'))
    replace("7.3 refresh audio from selected profile",
            'o=(0,c.getOnvifCameraStreams)(r),a=e.thirdPartyCameraInfo.errors',
            'o=e.thirdPartyCameraInfo.manualProfileOverride&&r.success'
            '?r.streams.filter(stream=>stream.profileToken===e.thirdPartyCameraInfo.profileToken)'
            ':(0,c.getOnvifCameraStreams)(r),a=e.thirdPartyCameraInfo.errors')
    # Discovery can refresh the RTSP URLs when the physical camera changes IP.
    rediscovery = 'const r=await(0,l.getCameraDetails)(t.hostname,e.port.toString(),e.username,e.password);if(r.success){const e=(0,u.getStreamData)(r),{hqStream:t,lqStream:o}=e.ok?e:{hqStream:null,lqStream:null};'
    replace("7.3 preserve selected profiles on IP change", rediscovery, '''const __tokens=e.manualProfileOverride
      ? [e.profileToken,e.profileTokenLQ].filter(Boolean) : [];
      const r=await (0,l.getCameraDetails)(t.hostname,e.port.toString(),e.username,e.password,
        {snapshotProfileTokens:__tokens.length ? [__tokens[0]] : []});
      if(r.success){
        const e=(0,u.getStreamData)(r);
        const {hqStream:t,lqStream:o}=__tokens.length
          ? {hqStream:r.streams.find(stream=>stream.profileToken===__tokens[0]),
             lqStream:r.streams.find(stream=>stream.profileToken===__tokens[1])}
          : e.ok?e:{hqStream:null,lqStream:null};''')
    replace("7.3 refresh selected snapshot on IP change",
            '...r.snapshotUri?{snapshotUrl:r.snapshotUri}:{}',
            '...(t?.snapshotUri??(__tokens.length?null:r.snapshotUri))'
            '?{snapshotUrl:t?.snapshotUri??r.snapshotUri}:{}')

    credentials = '.and(a.z.object({username:a.z.string(),password:a.z.string()}))'
    replace("7.3 adoption request schema", credentials,
            credentials[:-3] + ',profileTokens:a.z.array(a.z.string()).optional(),macSalt:a.z.string().optional(),'
            'rtspOnly:a.z.boolean().optional(),manualStreams:a.z.array(a.z.object({uri:a.z.string().regex(/^rtsps?:\\/\\//i),'
            'quality:a.z.string().optional(),name:a.z.string().optional(),encoding:a.z.string().optional(),'
            'width:a.z.number().optional(),height:a.z.number().optional(),hasAudio:a.z.boolean().optional(),'
            'fps:a.z.number().optional(),bitrate:a.z.number().optional()})).optional()}))')
    for request in ('n={camera:t,username:i,password:a,user:e.user}', 'else n={host:o,username:i,password:a,user:e.user}'):
        replace("7.3 pass adoption options", request,
                request[:-1] + ',profileTokens:e.body.profileTokens,macSalt:e.body.macSalt,rtspOnly:e.body.rtspOnly,manualStreams:e.body.manualStreams}')

    # Match the stock adoption route's permission checks and request validation.
    permissions = '''(0,_.validateUserPermission)(c.AccessMode.CREATE,"camera"),
      (0,E.validateGranularUserPermission)(d.GranularAccess.SETTINGS_EDIT,c.AccessMode.CREATE,s.NvrDecalModel.modelKey,n.CameraDecalModel.modelKey),'''
    routes = '''T.route({
      method:v.MethodNames.POST,path:"/third-party-cameras/probe",
      description:"Probe an ONVIF camera for available streams",summary:"Probe ONVIF streams",tags:A,
      schema:{requestBody:{content:{[h.ContentTypes.JSON]:{schema:I}}},
        responses:(0,g.defaultJsonResponse)({[y.StatusCodes.OK]:{description:"Probe result"},
          [y.StatusCodes.BAD_REQUEST]:{description:"Unsupported camera"}})},
      handlers:[''' + permissions + '''(0,m.createPayloadValidator)("body",I),async function(req,res) {
        const {id,host,username,password}=req.body;
        const camera=id ? this.store.findByPk("camera",id) : null;
        if(id&&!camera) throw new u.NotFoundError({info:{entity:"camera",id}});
        const result=await (0,l.publish)("thirdPartyCameras.probe",{...(camera?{camera}:{host}),username,password,user:req.user});
        result?res.json(result):res.status(400).end();
      }]
    });
    const __onvifHelperHtml=''' + json.dumps(HTML) + ''';
    T.route({
      method:v.MethodNames.GET,path:"/third-party-cameras/onvif-helper",
      description:"ONVIF onboarding helper UI",summary:"ONVIF onboarding helper UI",tags:A,
      schema:{responses:(0,g.defaultJsonResponse)({[y.StatusCodes.OK]:{description:"HTML page"}})},
      handlers:[''' + permissions + '''async function(req,res) {
        let html;
        try { html=r(973024).readFileSync("/etc/unifi-protect/onvif-mod/onvif_helper.html","utf8"); }
        catch { html=__onvifHelperHtml; }
        res.setHeader("Content-Type","text/html; charset=utf-8");
        res.status(200).end(html);
      }]
    });
    '''
    replace("7.3 register helper and probe routes", 't.json(a.apiSerialize())}]}),t.thirdPartyCamerasRouter=T}',
            't.json(a.apiSerialize())}]});' + routes + 't.thirdPartyCamerasRouter=T}')
    return changes


def main():
    parser = argparse.ArgumentParser(description="Build a patched copy of the Protect service bundle.")
    parser.add_argument("--input", type=Path, default=Path("/usr/share/unifi-protect/app/service.js"))
    parser.add_argument("--output", type=Path, default=Path("/usr/share/unifi-protect/app/service.js.new"))
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("--input and --output must be different files")
    if args.output.exists() and args.input.samefile(args.output):
        parser.error("--input and --output must not refer to the same file")

    src = args.input.read_text(encoding="utf-8")
    changes = protect_7_3_edits() if ADOPT_7_3 in src else edits
    for label, old, new in changes:
        count = src.count(old)
        if count != 1:
            sys.exit(f"ABORT: anchor for [{label}] found {count} times (expected 1)")
        src = src.replace(old, new, 1)
        print(f"ok: {label}")

    args.output.write_text(src, encoding="utf-8")
    print("WROTE", args.output, "bytes=", len(src.encode("utf-8")))


if __name__ == "__main__":
    main()
