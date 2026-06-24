#!/usr/bin/env python3
import json, sys, os

SRC = "/usr/share/unifi-protect/app/service.js"
OUT = "/usr/share/unifi-protect/app/service.js.new"

src = open(SRC, "r", encoding="utf-8", errors="strict").read()

edits = []  # (label, old, new)

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

# R4: adopt subscriber -> (a) honor selected profileTokens before building channels;
#     (b) optionally build channels from caller-supplied manual RTSP URLs for streams
#         the camera doesn't expose over ONVIF, e.g. a Tapo telephoto lens (issue #3);
#     (c) use the chosen source's per-profile snapshot URI as the thumbnail (issue #2).
edits.append((
 "R4 adopt stream selection + manual streams + per-source snapshot",
 r'''const{streams:E,hqStream:_,lqStream:T,encoding:A}=(0,p.getStreamData)(S),R=S.snapshotUri;''',
 r'''const __man=Array.isArray(t.manualStreams)?t.manualStreams.filter(m=>m&&m.uri):[],__sel=Array.isArray(t.profileTokens)&&t.profileTokens.length>0?t.profileTokens:null,__Sx=__sel?{...S,streams:S.streams.filter(x=>__sel.includes(x.profileToken)).sort((a,b)=>__sel.indexOf(a.profileToken)-__sel.indexOf(b.profileToken))}:S,__Sf=__man.length>0?{...S,ptz:!1,streams:__man.map((m,i)=>({resolution:{width:Number(m.width)||(0===i?1920:640),height:Number(m.height)||(0===i?1080:480)},encoding:m.encoding||"h264",quality:"",bitrate:Number(m.bitrate)>0?Number(m.bitrate):(0===i?2048:512),fps:Number(m.fps)>0?Number(m.fps):30,uri:m.uri,hasAudio:!!m.hasAudio,profileToken:"manual-"+i,profileName:m.name||"Manual stream "+(i+1),videoSourceToken:t.macSalt||"manual",snapshotUri:void 0}))}:__sel&&__Sx.streams.length>0?__Sx:S;const{streams:E,hqStream:_,lqStream:T,encoding:A}=(0,p.getStreamData)(__Sf),R=t.snapshotUrl||(_&&_.snapshotUri)||S.snapshotUri;const __rdct=function(u){return u?String(u).replace(/\/\/[^/@]*@/,"//<redacted>@").replace(/([?&](?:username|password|user|pass|token|auth))=[^&]*/gi,"$1=<redacted>"):u};f.info("[onvif-mod] adopt "+v+":"+y+" mode="+(__man.length>0?"manual":__sel?"selected":"auto")+"; "+E.length+" stream(s); hq="+(_?_.resolution.width+"x"+_.resolution.height+" "+_.encoding:"?")+"; ptz="+(__Sf.ptz?"on":"off")+"; audio="+!!(_&&_.hasAudio)+"; snapshot="+(R?(t.snapshotUrl?"manual-url":"onvif"):"none")+"; salted="+!!t.macSalt+"; hqUri="+__rdct(_&&_.uri));''',
))

# R14: build the camera settings from the (manual-aware) __Sf instead of S, so manual
#   streams adopt with PTZ disabled. A raw RTSP stream has no ONVIF PTZ binding, but the
#   manual camera was inheriting ptzControlEnabled from the wide-lens probe (S.ptz=true);
#   the iOS/web app then fires /ptz/home + /enable-control, times out, and crashes. __Sf
#   carries ptz:false for manual adopts and S's own ptz otherwise. (issue #10)
edits.append((
 "R14 adopt camera settings from __Sf (ptz off for manual)",
 r'''(0,m.getOnvifDefaultCameraSettings)(e.store,S,E)''',
 r'''(0,m.getOnvifDefaultCameraSettings)(e.store,__Sf,E)''',
))

# R5: adopt subscriber -> optional per-source MAC salt so multiple cameras behind one endpoint stay distinct
edits.append((
 "R5 adopt mac salt",
 r'''const e=await(0,u.getMAC)(v,S);n.default.ok(e,"Failed to get MAC address"),h=null!==(r=o.findByMac("camera",e))&&void 0!==r?r:o.createRecord("camera",{mac:e})''',
 r'''let e=await(0,u.getMAC)(v,S);n.default.ok(e,"Failed to get MAC address"),t.macSalt&&(e=(()=>{const z=String(e)+"|"+String(t.macSalt);let q=2166136261;for(let i=0;i<z.length;i++){q=(q^z.charCodeAt(i))>>>0,q=Math.imul(q,16777619)>>>0}let w=1540483477;for(let i=z.length-1;i>=0;i--){w=(w^z.charCodeAt(i))>>>0,w=Math.imul(w,16777619)>>>0}const b=[q>>>24&255,q>>>16&255,q>>>8&255,q&255,w>>>8&255,w&255];return b[0]=b[0]&254|2,b.map(x=>x.toString(16).padStart(2,"0")).join("").toUpperCase()})()),h=null!==(r=o.findByMac("camera",e))&&void 0!==r?r:o.createRecord("camera",{mac:e})''',
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
 r'''t.probe=async(e,t)=>{const{username:c,password:g}=t;let v,y;if("camera"in t){const h=t.camera;v=h.host,y=h.thirdPartyCameraInfo.port}else{if(!("host"in t))throw new Error("Invalid probe parameters");[v,y="80"]=t.host.split(":")}n.default.ok(v,"Missing camera host"),n.default.ok(y,"Missing camera port");const S=await(0,l.getCameraDetails)(v,y.toString(),c,g,{});if(!S.success)throw new s.UnauthorizedError({details:S.errors});const G=new Map;for(const st of S.streams){const en=(st.encoding||"").toLowerCase();if(!en.includes("264")&&!en.includes("265"))continue;const k=st.videoSourceToken||"__default__";G.has(k)||G.set(k,[]),G.get(k).push({profileToken:st.profileToken,profileName:st.profileName||st.profileToken,encoding:st.encoding,width:st.resolution?st.resolution.width:0,height:st.resolution?st.resolution.height:0,fps:st.fps,bitrate:st.bitrate,hasAudio:!!st.hasAudio})}const cams=Array.from(G.entries()).map(([k,arr],idx)=>(arr.sort((a,b)=>b.width-a.width),{videoSourceToken:"__default__"===k?null:k,label:"__default__"===k?S.name||"Camera "+(idx+1):(S.name||"Camera")+" #"+(idx+1),streams:arr}));f.info("[onvif-mod] probe "+v+":"+y+' -> "'+(S.name||"camera")+'"'+(S.device?" ("+S.device.manufacturer+" "+S.device.model+")":"")+"; "+cams.length+" source(s), "+S.streams.length+" stream(s); "+cams.map(function(c){return c.label+"=["+c.streams.map(function(s){return s.width+"x"+s.height+" "+s.encoding}).join(" | ")+"]"}).join("; "));return{name:S.name,ptz:!!S.ptz,success:!0,errors:S.errors,host:v,port:String(y),cameras:cams}};t.adopt=async(e,t)=>{var r;const{store:o}=e,{username:c,password:g}=t;try{let h,v,y;''',
))

# R8: extend adopt/probe request schema to allow profileTokens + macSalt + manualStreams
edits.append((
 "R8 router schema profileTokens/macSalt/manualStreams",
 r'''.and(i.z.object({username:i.z.string(),password:i.z.string()}))''',
 r'''.and(i.z.object({username:i.z.string(),password:i.z.string(),profileTokens:i.z.array(i.z.string()).optional(),macSalt:i.z.string().optional(),snapshotUrl:i.z.string().optional(),manualStreams:i.z.array(i.z.object({uri:i.z.string(),quality:i.z.string().optional(),name:i.z.string().optional(),encoding:i.z.string().optional(),width:i.z.number().optional(),height:i.z.number().optional(),hasAudio:i.z.boolean().optional(),fps:i.z.number().optional(),bitrate:i.z.number().optional()})).optional()}))''',
))

# R9: thread selection through adopt route (camera branch)
edits.append((
 "R9 router adopt n camera branch",
 r'''n={camera:t,username:i,password:a,user:e.user}''',
 r'''n={camera:t,username:i,password:a,user:e.user,profileTokens:e.body.profileTokens,macSalt:e.body.macSalt,manualStreams:e.body.manualStreams,snapshotUrl:e.body.snapshotUrl}''',
))

# R10: thread selection through adopt route (host branch)
edits.append((
 "R10 router adopt n host branch",
 r'''else n={host:o,username:i,password:a,user:e.user}''',
 r'''else n={host:o,username:i,password:a,user:e.user,profileTokens:e.body.profileTokens,macSalt:e.body.macSalt,manualStreams:e.body.manualStreams,snapshotUrl:e.body.snapshotUrl}''',
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
 r'''t.syncOnvifCameraConfig=async(e,t,r)=>{var i,d,l,u,p,m,f,g,h,v,y,S,E,_;if(!r.success)return;if(t.thirdPartyCameraInfo&&"string"==typeof t.thirdPartyCameraInfo.profileToken&&0===t.thirdPartyCameraInfo.profileToken.indexOf("manual")){s.debug("[onvif-mod] skip ONVIF config re-sync for manual "+t.logId);return}''',
))

# R13: same guard for updateOnvifCameraInfo (re-probes ONVIF to refresh hasAudio/
#   errors/featureFlags) — skip it for manual-stream cameras so they aren't probed
#   against the wrong lens. (issue #7)
edits.append((
 "R13 skip ONVIF info refresh for manual streams",
 r'''t.updateOnvifCameraInfo=async(e,t)=>{i.default.ok(e.host,"Camera host is not defined")''',
 r'''t.updateOnvifCameraInfo=async(e,t)=>{if(e.thirdPartyCameraInfo&&"string"==typeof e.thirdPartyCameraInfo.profileToken&&0===e.thirdPartyCameraInfo.profileToken.indexOf("manual")){c.debug("[onvif-mod] skip ONVIF info refresh for manual "+e.logId);return}i.default.ok(e.host,"Camera host is not defined")''',
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

# ---- apply ----
for label, old, new in edits:
    cnt = src.count(old)
    if cnt != 1:
        print(f"ABORT: anchor for [{label}] found {cnt} times (expected 1)")
        sys.exit(1)
    src = src.replace(old, new, 1)
    print(f"ok: {label}")

open(OUT, "w", encoding="utf-8").write(src)
print("WROTE", OUT, "bytes=", len(src))
