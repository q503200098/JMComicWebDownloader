"""
统一路径管理 - 支持 Docker / Windows exe / macOS app / 本地开发
"""
import os
import sys
from pathlib import Path


def detect_dirs():
    """
    返回 (DATA_DIR, DOWNLOADS_DIR)
    - DATA_DIR: 存放 ids.txt, account.txt, state.json, done.txt, logs/, config.yml
    - DOWNLOADS_DIR: 漫画下载目录（外挂卷/本地）
    """
    # Docker 环境: /app 目录存在
    if os.path.isdir("/app"):
        data = Path("/app")
        downloads = Path("/downloads")
        return data, downloads

    # 打包后的 exe / app (PyInstaller frozen)
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # macOS .app bundle 签名后只读，数据放到用户目录
            data = Path.home() / ".jmcomic-web"
            downloads = Path.home() / "Downloads" / "jmcomic-web"
        else:
            # Windows exe 便携模式，数据放 exe 同级
            base = Path(sys.executable).parent
            data = base
            downloads = base / "downloads"
        return data, downloads

    # 本地 Python 开发
    base = Path(__file__).resolve().parent
    return base, base / "downloads"


DATA_DIR, DOWNLOADS_DIR = detect_dirs()

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 各文件路径
IDS_FILE = DATA_DIR / "ids.txt"
ACCOUNT_FILE = DATA_DIR / "account.txt"
STATE_FILE = DATA_DIR / "state.json"
DONE_FILE = DATA_DIR / "done.txt"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_config_path():
    """动态生成 jmcomic 配置文件，返回路径字符串（base_dir 用正斜杠避免 yaml 转义）"""
    config_path = DATA_DIR / "config.yml"
    content = (
        "dir_rule:\n"
        f"  base_dir: {DOWNLOADS_DIR.as_posix()}\n"
        "  rule: Bd_Aid_Pid\n"
        "\n"
        "download:\n"
        "  image:\n"
        "    suffix: .jpg\n"
    )
    config_path.write_text(content, encoding="utf-8")
    return str(config_path)
