"""
Xuất ảnh phản hồi của người dùng sang data/raw/ để train phiên bản model tiếp theo.

    python -m ml.export_feedback --dry-run
    python -m ml.export_feedback
    python -m ml.export_feedback --only-corrected

Cần đọc/ghi CSDL (bảng feedback_images) nên phần xử lý nằm trong lệnh Django
`manage.py export_feedback` (apps/feedback/services.py). Script này chỉ chuyển tiếp tham số,
để mọi bước của pipeline ML đều chạy được từ thư mục ml/.
"""
import subprocess
import sys

from ml.common import ROOT


def main():
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
    cmd = [sys.executable, str(ROOT / "manage.py"), "export_feedback", *sys.argv[1:]]
    sys.exit(subprocess.run(cmd, cwd=ROOT).returncode)


if __name__ == "__main__":
    main()
