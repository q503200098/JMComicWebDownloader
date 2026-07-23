"""
Windows exe 打包脚本（PyInstaller）
用法: python build_exe.py
生成: dist/JMComic-Web.exe（便携单文件，数据存放在 exe 同级目录）
"""
import subprocess
import sys


def main():
    # 确保已安装 pyinstaller
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name", "JMComic-Web",
        "--console",
        # jmcomic 与 Pillow 的动态导入
        "--hidden-import", "jmcomic",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--collect-all", "jmcomic",
        "--collect-all", "PIL",
        # 入口
        "app.py",
    ]
    subprocess.check_call(cmd)
    print("\n打包完成: dist/JMComic-Web.exe")
    print("运行时数据（ids.txt/account.txt/state.json/logs/downloads）会自动生成在 exe 同级目录")


if __name__ == "__main__":
    main()
