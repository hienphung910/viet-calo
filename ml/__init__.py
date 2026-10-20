import sys

# Console Windows mặc định dùng bảng mã cp1252 khi output bị chuyển hướng (pipe, ghi ra file)
# -> in tiếng Việt bị UnicodeEncodeError. Ép stdout/stderr sang UTF-8 cho mọi script trong ml/.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower().replace("-", "") != "utf8":
        _stream.reconfigure(encoding="utf-8", errors="replace")
