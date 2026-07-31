# -*- coding: utf-8 -*-
"""비세메 립싱크 POC — 한글 음절의 모음→입모양(A/O/E/닫힘) 매핑 + 음절 타이밍으로 입 움직임."""
import os, sys, subprocess, numpy as np
sys.path.insert(0, r"D:\saju_agent"); sys.stdout.reconfigure(encoding="utf-8")
from backend.app.services.video import tts
SCR = r"C:\Users\orion\AppData\Local\Temp\claude\D--saju-agent\931184cc-74b4-4e63-811a-16dabf38246e\scratchpad\viseme"
LIB = r"D:\saju_agent\backend\app\services\assets\video_stills"
W, H = 1080, 1920
SHAPES = {"closed": f"{LIB}/토끼_청년.png", "A": f"{SCR}/vis_A.png", "O": f"{SCR}/vis_O.png", "E": f"{SCR}/vis_E.png"}
# W×H로 cover-crop 미리
from PIL import Image
def cover(p):
    im = Image.open(p).convert("RGB"); sw, sh = im.size; sc = max(W/sw, H/sh)
    im = im.resize((int(sw*sc), int(sh*sc))); nw, nh = im.size
    return im.crop(((nw-W)//2, (nh-H)//2, (nw-W)//2+W, (nh-H)//2+H))
for k, p in list(SHAPES.items()):
    o = f"{SCR}/cc_{k}.png"; cover(p).save(o); SHAPES[k] = o

_A = {0, 1, 2, 3, 9, 10}; _O = {8, 11, 12, 13, 14, 15, 17}

def viseme(ch):
    if not ("가" <= ch <= "힣"):
        return None
    j = (ord(ch) - 0xAC00) // 28 % 21
    return "A" if j in _A else "O" if j in _O else "E"

line = "청년이 되니 새로운 도전을 두려워하지 않게 됐어. 열정을 다해 나아가고 있어."
wav = f"{SCR}/ls.wav"; tts.synth("openai", line, wav, gender="male", stage="청년")
# 진폭 포락선(30fps)
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
dur = len(a) / 16000.0; fps = 30; nF = int(dur * fps); hop = 16000 // fps
amp = np.array([np.sqrt(np.mean(a[i*hop:(i+1)*hop]**2) + 1e-9) for i in range(nF)])
thr = max(0.02, amp.max() * 0.15)
syl = [c for c in line if "가" <= c <= "힣"]           # 한글 음절만
visq = [viseme(c) for c in syl]
sdur = dur / max(1, len(syl))
# 프레임별 입모양: 무음=닫힘, 유음=현재 음절 모음
seq = []
for f in range(nF):
    if amp[f] < thr:
        seq.append("closed")
    else:
        si = min(len(visq) - 1, int((f / fps) / sdur))
        seq.append(visq[si] or "E")
# 디바운스(최소 3프레임 유지)
out = [seq[0]]; cur = seq[0]; run = 1
for v in seq[1:]:
    if v == cur or run < 2:
        out.append(cur); run += 1
    else:
        cur = v; out.append(cur); run = 1
seq = out
# RLE concat
lst = f"{SCR}/ls.txt"; lines = []
i = 0
while i < len(seq):
    j = i
    while j < len(seq) and seq[j] == seq[i]:
        j += 1
    lines.append(f"file '{SHAPES[seq[i]].replace(chr(92),'/')}'"); lines.append(f"duration {(j-i)/fps:.4f}"); i = j
lines.append(f"file '{SHAPES[seq[-1]].replace(chr(92),'/')}'")
open(lst, "w", encoding="utf-8").write("\n".join(lines))
out_mp4 = r"D:\saju_agent\output\립싱크_POC_토끼.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                "-filter_complex", "[0:v]fps=30,setsar=1[v]", "-map", "[v]", "-map", "1:a", "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", out_mp4], check=True)
print(f"음절수={len(syl)} 프레임={nF} 입모양분포={ {s:seq.count(s) for s in set(seq)} }", flush=True)
# 연속 프레임 추출(입 변화 확인)
for i, t in enumerate([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", out_mp4, "-frames:v", "1", "-vf", "crop=700:500:190:760,scale=240:171", f"{SCR}/ls_{i}.png"], capture_output=True)
print("done", flush=True)
