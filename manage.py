#!/usr/bin/env python
"""Điểm vào các lệnh quản trị Django (runserver, migrate, seed_foods...)."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Console Windows dùng cp1252 khi output bị chuyển hướng -> lỗi khi in tiếng Việt. Ép UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
