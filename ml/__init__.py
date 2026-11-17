import sys

# để in tiếng Việt ra console Windows không bị lỗi mã hóa
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower().replace("-", "") != "utf8":
        _stream.reconfigure(encoding="utf-8", errors="replace")
