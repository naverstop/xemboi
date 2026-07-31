# -*- coding: utf-8 -*-
"""말하는 호랑이 통합: 입 열림/닫힘 flap(SVD 대신 → 뭉개짐 없음 + 말하는 입) + 나이목소리(애기는 피치업)
   + 자연 텍스트 + 세로워터마크/옅은자막 + fadewhite 전환 + 4K. 단계단계 검증용."""
import os, sys, time, subprocess, textwrap, json
import numpy as np
sys.path.insert(0, r"D:\saju_agent"); sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFont
from backend.app.core.db import get_session_factory
from backend.app.repositories.models import ChatMessage, ChatSession
from backend.app.services.video.source import fetch_saju_video_source
from backend.app.services.video import scenario as scen, tts

SCR=r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad"
LIB=r"D:\saju_agent\backend\app\services\assets\video_stills"
WORK=f"{SCR}/talkwork"; OUT=r"D:\saju_agent\output\말하는호랑이_통합.mp4"
os.makedirs(WORK, exist_ok=True)
NOTO=r"C:\Windows\Fonts\NotoSansKR-VF.ttf"; SEAL=r"D:\saju_agent\backend\app\services\assets\seal.png"
W,H=1080,1920

def font(sz,bold=True):
    f=ImageFont.truetype(NOTO,sz)
    if bold:
        try: f.set_variation_by_name("Bold")
        except: pass
    return f
def render_overlay(title,subtitle,out):
    img=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(img)
    ft=font(int(W*0.044)); tb=d.textbbox((0,0),title,font=ft); tw=tb[2]-tb[0]; th=tb[3]-tb[1]; ty=int(H*0.045); pad=int(W*0.025)
    d.rounded_rectangle([W//2-tw//2-pad,ty-int(H*0.01),W//2+tw//2+pad,ty+th+int(H*0.012)],radius=22,fill=(0,0,0,120))
    d.text((W//2,ty+th//2),title,font=ft,fill=(255,255,255,235),anchor="mm")
    fs=font(int(W*0.056)); txt=textwrap.fill(subtitle,18)
    bb=d.multiline_textbbox((0,0),txt,font=fs,spacing=14,align="center"); sh=bb[3]-bb[1]; cy=int(H*0.82)
    d.rounded_rectangle([W*0.05,cy-sh//2-int(H*0.018),W*0.95,cy+sh//2+int(H*0.018)],radius=26,fill=(0,0,0,72))
    for dx,dy in [(-2,-2),(2,-2),(-2,2),(2,2)]: d.multiline_text((W//2+dx,cy+dy),txt,font=fs,fill=(0,0,0,220),anchor="mm",spacing=14,align="center")
    d.multiline_text((W//2,cy),txt,font=fs,fill=(255,255,255,255),anchor="mm",spacing=14,align="center")
    try:
        ssz=int(W*0.10); sx=W-ssz-int(W*0.022); sy=int(H*0.095)
        seal=Image.open(SEAL).convert("RGBA").resize((ssz,ssz)); a=seal.split()[3].point(lambda v:int(v*0.85)); seal.putalpha(a); img.alpha_composite(seal,(sx,sy))
        fb=font(int(W*0.036)); cx=W-int(W*0.055); y=sy+ssz+int(H*0.018)
        for ch in "인생상담친구":
            for dx,dy in [(-2,-2),(2,-2),(-2,2),(2,2)]: d.text((cx+dx,y+dy),ch,font=fb,fill=(0,0,0,200),anchor="mm")
            d.text((cx,y),ch,font=fb,fill=(255,255,255,235),anchor="mm"); y+=int(W*0.052)
    except: pass
    img.save(out); return out
def dur(f):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f],capture_output=True,text=True)
    try: return float(r.stdout.strip())
    except: return 3.0
def pitch(src,out,semi):
    fct=2**(semi/12); subprocess.run(["ffmpeg","-y","-loglevel","error","-i",src,"-af",f"asetrate=24000*{fct:.4f},aresample=24000,atempo={1/fct:.4f}",out],check=True); return out

F=get_session_factory()
with F() as db:
    rows=db.query(ChatMessage.id).join(ChatSession,ChatSession.session_id==ChatMessage.session_id).filter(ChatMessage.role=="assistant",ChatSession.chart_json.isnot(None)).order_by(ChatMessage.id.desc()).limit(60).all()
    mid=None
    for (cid,) in rows:
        s=fetch_saju_video_source(db,cid,is_admin=True)
        if s.zodiac=="호랑이": mid,src=cid,s; break
    print(f"대상 {mid} 띠={src.zodiac}",flush=True)
t0=time.time(); scn=scen.generate_scenario(src,seconds=95); title="호랑이님의 사주영상"
json.dump(scn,open(f"{WORK}/scn.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
# 생애 흐름 보장: 위치 기반으로 도입→청년→중년→노년→마무리 강제(LLM 누락 방지)
_ORDER=["도입","청년","중년","노년","마무리"]; _N=len(scn["scenes"])
for _idx,_sc in enumerate(scn["scenes"]):
    _sc["stage"]=_ORDER[min(4,int(round((_idx/(_N-1) if _N>1 else 0)*4)))]
print(f"[{time.time()-t0:.0f}s] {len(scn['scenes'])}컷 {sum(len(s['line']) for s in scn['scenes'])}자 단계:{[s['stage'] for s in scn['scenes']]}",flush=True)

def envelope(wav, fps=30):
    """오디오 RMS 진폭 포락선(프레임당). ffmpeg로 PCM 디코드 후 numpy RMS."""
    raw=subprocess.run(["ffmpeg","-v","error","-i",wav,"-ac","1","-ar","16000","-f","s16le","-"],capture_output=True).stdout
    a=np.frombuffer(raw,dtype=np.int16).astype(np.float32)/32768.0
    hop=16000//fps
    if len(a)<hop: return np.zeros(1)
    n=len(a)//hop
    return np.array([np.sqrt(np.mean(a[k*hop:(k+1)*hop]**2)+1e-9) for k in range(n)])

def dwell(st, minrun=3):
    """최소 유지(0.1s) — 입이 프레임마다 떨리지 않게."""
    st=list(st); out=[st[0]]; cur=st[0]; run=1
    for v in st[1:]:
        if v==cur or run<minrun: out.append(cur); run=run+1 if v==cur else run+1
        else: cur=v; out.append(cur); run=1
    return np.array(out)

def mouth_states(wav, pad=0.6, fps=30):
    """진폭>임계 → 입 열림(1), 아니면 닫힘(0). 무음 패딩=닫힘."""
    rms=envelope(wav,fps)
    if rms.max()<1e-6: st=np.zeros(len(rms),dtype=int)
    else:
        thr=max(0.02, rms.max()*0.16); st=(rms>thr).astype(int); st=dwell(st,3)
    return np.concatenate([st, np.zeros(int(pad*fps),dtype=int)])

scene_clips=[]
for i,sc in enumerate(scn["scenes"]):
    stage=sc.get("stage","도입")
    wav=tts.synth("openai",sc["line"],f"{WORK}/v{i}.wav",gender=src.gender,stage=stage,emotion=sc.get("emotion",""))
    if stage in ("도입","유년"):  # 애기 목소리: 피치업
        wav=pitch(wav,f"{WORK}/v{i}_baby.wav",4)
    d=dur(wav); pad=0.6; sdur=d+pad
    st=mouth_states(wav,pad=pad,fps=30)
    closed=f"{LIB}/호랑이_{stage}.png"; opn=f"{LIB}/호랑이_{stage}_open.png"
    if not os.path.exists(opn): opn=closed
    # 진폭 상태 → RLE → concat 리스트(닫힘/열림 스틸을 구간별로)
    lst=f"{WORK}/flap{i}.txt"; lines=[]; j=0; n=len(st)
    while j<n:
        k=j
        while k<n and st[k]==st[j]: k+=1
        img=(opn if st[j]==1 else closed).replace(chr(92),'/')
        lines.append(f"file '{img}'"); lines.append(f"duration {(k-j)/30.0:.4f}"); j=k
    lines.append(f"file '{(opn if st[-1]==1 else closed).replace(chr(92),'/')}'")  # concat 규칙: 마지막 프레임
    open(lst,"w",encoding="utf-8").write("\n".join(lines))
    ov=render_overlay(title,sc["line"],f"{WORK}/ov{i}.png"); sc_out=f"{WORK}/scene{i}.mp4"
    subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,"-i",wav,"-i",ov,
        "-filter_complex","[0:v]fps=30,scale=1080:1920,setsar=1[v0];[v0][2:v]overlay=0:0[v];[1:a]apad=pad_dur=0.6[a]",
        "-map","[v]","-map","[a]","-t",f"{sdur:.2f}","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k",sc_out],check=True)
    scene_clips.append(sc_out); print(f"  scene{i} {stage} {d:.1f}s 입열림{100*st.mean():.0f}%",flush=True)

T=0.45; durs=[dur(c) for c in scene_clips]; inp=[]
for c in scene_clips: inp+=["-i",c]
parts=[]; pv="[0:v]"; pa="[0:a]"; acc=durs[0]
for i in range(1,len(scene_clips)):
    off=max(0.1,acc-T); nv=f"[v{i}]"; na=f"[a{i}]"
    parts.append(f"{pv}[{i}:v]xfade=transition=fadewhite:duration={T}:offset={off:.3f}{nv}")
    parts.append(f"{pa}[{i}:a]acrossfade=d={T}{na}"); pv,pa=nv,na; acc=acc+durs[i]-T
parts.append(f"{pv}scale=2160:3840:flags=lanczos[vout]"); parts.append(f"{pa}loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
subprocess.run(["ffmpeg","-y","-loglevel","error",*inp,"-filter_complex",";".join(parts),"-map","[vout]","-map","[aout]",
    "-c:v","hevc_nvenc","-preset","p5","-rc","vbr","-cq","30","-pix_fmt","p010le","-maxrate","6M","-bufsize","12M","-tag:v","hvc1","-gpu","0",
    "-c:a","aac","-b:a","128k","-movflags","+faststart",OUT],check=True)
print(f"[{time.time()-t0:.0f}s] 완료 -> {OUT}",flush=True)
dt=dur(OUT)
for tag,t in [("a",dt*0.06),("a2",dt*0.1),("b",dt*0.5),("c",dt*0.92)]:
    subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",f"{t:.1f}","-i",OUT,"-frames:v","1","-vf","scale=300:533",f"{SCR}/tk_{tag}.png"],check=False)
print(f"규격: {subprocess.run(['ffprobe','-v','error','-show_entries','stream=width,height','-show_entries','format=duration,size','-of','default=nw=1',OUT],capture_output=True,text=True).stdout}",flush=True)
