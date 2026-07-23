import os
import re
import shutil
import zipfile
import sys

# 让 scripts/ 下的文件能导入根目录的 paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jmcomic
import paths
import xml.sax.saxutils as saxutils


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def create_comicinfo(album):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
<Title>{saxutils.escape(album.name)}</Title>
<Series>{saxutils.escape(album.name)}</Series>
<Summary>{saxutils.escape(album.description)}</Summary>
<Writer>{saxutils.escape(album.author)}</Writer>
<Genre>{saxutils.escape(album.tags[0] if album.tags else "")}</Genre>
<LanguageISO>zh</LanguageISO>
</ComicInfo>
'''


def make_cbz(source_base, cbz_path, album):
    xml = create_comicinfo(album)
    all_images = []

    for photo_id, photo_index, photo_title in album.episode_list:
        chapter_dir = os.path.join(source_base, str(photo_id))
        if not os.path.isdir(chapter_dir):
            print("警告: 章节目录不存在:", chapter_dir)
            continue

        images = sorted(
            f for f in os.listdir(chapter_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        )
        for img in images:
            all_images.append(os.path.join(chapter_dir, img))

    if not all_images:
        print("未找到任何图片")
        return

    # 智能封面
    all_images = pick_cover_first(all_images)

    print(f"共 {len(album.episode_list)} 章, {len(all_images)} 页")

    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as z:
        for i, img_path in enumerate(all_images, 1):
            ext = os.path.splitext(img_path)[1]
            new_name = f"{i:05d}{ext}"
            z.write(img_path, new_name)
        z.writestr("ComicInfo.xml", xml.encode("utf-8"))


def pick_cover_first(images):
    from PIL import Image
    cover_idx = None
    for i, path in enumerate(images):
        try:
            with Image.open(path) as img:
                w, h = img.size
                if w < 300 or h < 400:
                    continue
                ratio = h / w
                if 0.6 <= ratio <= 1.8:
                    cover_idx = i
                    break
        except Exception:
            continue
    if cover_idx is not None and cover_idx > 0:
        cover = images.pop(cover_idx)
        images.insert(0, cover)
        print(f"封面: 选中第 {cover_idx + 1} 张图作为封面")
    else:
        print("封面: 使用默认第一张图（未找到合适的封面图）")
    return images


def run():
    IDS_FILE = str(paths.IDS_FILE)
    DONE_FILE = str(paths.DONE_FILE)
    CONFIG = paths.get_config_path()
    BASE_DIR = str(paths.DOWNLOADS_DIR)

    if not os.path.exists(IDS_FILE):
        print("没有找到 ids.txt")
        return

    with open(IDS_FILE, "r", encoding="utf-8") as f:
        ids = [line.strip() for line in f if line.strip()]

    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            done = set(line.strip() for line in f if line.strip())
    else:
        done = set()

    option = jmcomic.create_option_by_file(CONFIG)
    client = option.new_jm_client()

    for album_id in ids:

        if album_id in done:
            print("跳过已完成:", album_id)
            continue

        print("====================")
        print("开始下载:", album_id)
        print("====================")

        try:
            # 获取漫画详情（章节列表）
            album = client.get_album_detail(album_id)
            name = sanitize_filename(album.name)
            folder_name = f"{name} ({album_id})"
            save_dir = os.path.join(BASE_DIR, folder_name)
            os.makedirs(save_dir, exist_ok=True)

            cbz = os.path.join(save_dir, f"{folder_name}.cbz")
            if os.path.exists(cbz):
                print("已存在:", cbz)
                continue

            print(f"共 {len(album.episode_list)} 个章节")

            # 下载
            jmcomic.download_album(album_id, option)

            # 打包
            source = os.path.join(BASE_DIR, str(album_id))
            if not os.path.exists(source):
                print("找不到图片目录:", source)
                continue

            make_cbz(source, cbz, album)
            print("生成:", cbz)

            # 清理散图
            shutil.rmtree(source, ignore_errors=True)

            # 记录完成
            with open(DONE_FILE, "a", encoding="utf-8") as f:
                f.write(album_id + "\n")

            print("完成记录:", album_id)

        except Exception as e:
            print("失败:", album_id)
            print(e)

    print("====================")
    print("全部任务结束")
    print("====================")


if __name__ == "__main__":
    run()
