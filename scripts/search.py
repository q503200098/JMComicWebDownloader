import sys
import os

# 让 scripts/ 下的文件能导入根目录的 paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jmcomic
import paths


def search(keyword):
    """搜索漫画，返回 [(id, title), ...]"""
    if not keyword:
        return []
    CONFIG = paths.get_config_path()
    option = jmcomic.create_option_by_file(CONFIG)
    client = option.new_jm_client()
    result = client.search(keyword, 1, 0, "mr", "", "", None)
    return [(aid, title) for aid, title in result.iter_id_title()]


def main():
    if len(sys.argv) < 2:
        print("请输入关键词")
        return
    keyword = sys.argv[1]
    for aid, title in search(keyword):
        print(f"{aid}|{title}")


if __name__ == "__main__":
    main()
