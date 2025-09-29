import re
from pathlib import Path
def parse_log_for_metrics(log_path:str):
    t=Path(log_path).read_text(errors="ignore")
    br=None;py=None
    for pat in [r'Bitrate\s*\(kbps\)\s*[:=]\s*([0-9.]+)', r'Bitrate\s*[:=]\s*([0-9.]+)\s*kbps']:
        m=re.search(pat,t,flags=re.I)
        if m: br=float(m.group(1)); break
    for pat in [r'Y-?PSNR\s*\(dB\)\s*[:=]\s*([0-9.]+)', r'PSNR[-\s]*Y\s*[:=]\s*([0-9.]+)']:
        m=re.search(pat,t,flags=re.I)
        if m: py=float(m.group(1)); break
    return br,py
