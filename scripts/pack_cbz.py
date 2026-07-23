import os
import re
import shutil
import zipfile
import sys

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


def run():
    BASE_DIR = str(paths.DOWNLOADS_DIR)
    CONFIG = paths.get_config_path()
    option = jmcomic.create_option_by_file(CONFIG)
    client = option.new_jm_client()

    for folder in os.listdir(BASE_DIR):

        path = os.path.join(BASE_DIR, folder)

        if not os.path.isdir(path):
            continue

        # 尝试提取 album_id（假设目录名格式: 漫画名 (album_id)）
        album_id = None
        if "(" in folder and folder.endswith(")"):
            try:
                album_id = folder.split("(")[-1].rstrip(")")
            except:
                pass

        if not album_id:
            print("跳过未知目录:", folder)
            continue

        # 检查是否已有 CBZ
        cbz = os.path.join(path, f"{folder}.cbz")
        if os.path.exists(cbz):
            print("已存在:", cbz)
            continue

        print("处理:", folder, "album_id:", album_id)

        try:
            album = client.get_album_detail(album_id)
        except Exception as e:
            print("获取详情失败:", e)
            continue

        xml = create_comicinfo(album)
        all_images = []

        for photo_id, photo_index, photo_title in album.episode_list:
            chapter_dir = os.path.join(BASE_DIR, str(album_id), str(photo_id))
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
            print("未找到图片:", folder)
            continue

        print(f"共 {len(album.episode_list)} 章, {len(all_images)} 页")

        with zipfile.ZipFile(cbz, "w", zipfile.ZIP_DEFLATED) as z:
            for i, img_path in enumerate(all_images, 1):
                ext = os.path.splitext(img_path)[1]
                new_name = f"{i:05d}{ext}"
                z.write(img_path, new_name)
            z.writestr("ComicInfo.xml", xml.encode("utf-8"))

        # 清理散图目录
        source = os.path.join(BASE_DIR, str(album_id))
        if os.path.exists(source):
            shutil.rmtree(source, ignore_errors=True)

        print("完成:", cbz)


if __name__ == "__main__":
    run()
