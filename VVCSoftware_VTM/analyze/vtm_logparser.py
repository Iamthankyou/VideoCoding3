
# vtm_logparser.py
# Parse EncoderApp logs to obtain bitrate (kbps) and PSNR-Y for each run.
import re
from pathlib import Path

BITRATE_PATTERNS = [
    r'Bitrate\s*\(kbps\)\s*[:=]\s*([0-9.]+)',  # SUMMARY table
    r'Bitrate\s*[:=]\s*([0-9.]+)\s*kbps',      # plain line
    r'bitrate\s*[:=]\s*([0-9.]+)\s*kbps',
]
PSNRY_PATTERNS = [
    r'Y-?PSNR\s*\(dB\)\s*[:=]\s*([0-9.]+)',    # SUMMARY table
    r'PSNR[-\s]*Y\s*[:=]\s*([0-9.]+)',         # plain line
    r'Y\s*PSNR\s*[:=]\s*([0-9.]+)',
]

def parse_log_for_metrics(log_path: str):
    """
    Returns (bitrate_kbps, psnr_y) or (None, None) if not found.
    """
    text = Path(log_path).read_text(errors="ignore")
    br = None
    psnr_y = None
    for pat in BITRATE_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            br = float(m.group(1))
            break
    for pat in PSNRY_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            psnr_y = float(m.group(1))
            break
    return br, psnr_y
