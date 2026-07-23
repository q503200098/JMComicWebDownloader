import jmcomic
import os
import re
import shutil
import zipfile
import json
import sys
import xml.sax.saxutils as saxutils

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths


def sanitize_filename(name):
    """清理文件名中的非法字符（Windows兼容）"""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


# ======================
# XML
# ======================

def create_comicinfo(album):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
<Title>{saxutils.escape(album["name"])}</Title>
<Series>{saxutils.escape(album["name"])}</Series>
<Summary>{saxutils.escape(album.get("description", ""))}</Summary>
<Writer>{saxutils.escape(album.get("author", ""))}</Writer>
<Genre>{saxutils.escape(album.get("category", {}).get("title", ""))}</Genre>
<LanguageISO>zh</LanguageISO>
</ComicInfo>
'''


# ======================
# CBZ打包（按章节顺序合并）
# ======================

def make_cbz(source_base, cbz_path, album, episode_list):
    xml = create_comicinfo(album)
    all_images = []

    for photo_id, photo_index, photo_title in episode_list:
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

    # 智能封面：将适合做封面的图排到最前面
    all_images = pick_cover_first(all_images)

    print(f"共 {len(episode_list)} 章, {len(all_images)} 页")

    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as z:
        for i, img_path in enumerate(all_images, 1):
            ext = os.path.splitext(img_path)[1]
            new_name = f"{i:05d}{ext}"
            z.write(img_path, new_name)
        z.writestr("ComicInfo.xml", xml.encode("utf-8"))


# ======================
# 智能封面：选比例合适的图作为封面
# ======================

def pick_cover_first(images):
    """
    智能选封面：找到第一张符合封面特征的图，移到列表最前面。
    封面特征：
      - 宽高比在 0.6~1.8 之间（排除长条图和极宽横条）
      - 宽度 >= 300px 且高度 >= 400px（排除小图和广告条）
    如果找不到合适的，保持原序。
    """
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


# ======================
# 状态管理（追踪已下载的章节数）
# ======================

def load_state():
    if os.path.exists(paths.STATE_FILE):
        with open(paths.STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 向后兼容: 旧格式是纯数字，迁移为新格式
        migrated = {}
        for k, v in data.items():
            if isinstance(v, dict):
                migrated[k] = v
            else:
                migrated[k] = {"count": v, "title": "", "status": "连载中"}
        return migrated
    return {}


def save_state(state):
    with open(paths.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ======================
# 主流程
# ======================

def run():
    ACCOUNT_FILE = str(paths.ACCOUNT_FILE)
    CONFIG = paths.get_config_path()
    BASE_DIR = str(paths.DOWNLOADS_DIR)

    # 从文件读取账号
    if os.path.exists(ACCOUNT_FILE):
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if len(lines) >= 2:
            USERNAME = lines[0]
            PASSWORD = lines[1]
        else:
            print("错误: account.txt 格式不正确，需要两行（用户名和密码）")
            return
    else:
        print("错误: 未找到 account.txt，请先在网页上登录")
        return

    option = jmcomic.create_option_by_file(CONFIG)
    client = option.new_jm_client()
    state = load_state()

    # ======================
    # 登录
    # ======================

    def do_login():
        print("正在登录...")
        resp = client.login(USERNAME, PASSWORD)
        # 修复 cookie
        cookies = client.postman.meta_data["cookies"]
        cookies.update(dict(resp.resp.cookies))
        cookies["AVS"] = resp.res_data["s"]
        client.postman.meta_data["cookies"] = cookies
        print("登录成功:", resp.res_data["username"])
        return resp

    do_login()

    # ======================
    # 下载单本
    # ======================

    def download_album(album_id, album):
        name = sanitize_filename(album["name"])
        folder_name = f"{name} ({album_id})"
        save_dir = os.path.join(BASE_DIR, folder_name)
        os.makedirs(save_dir, exist_ok=True)

        cbz = os.path.join(save_dir, f"{folder_name}.cbz")

        # 获取远端章节列表
        print(f"\n检查: {name} ({album_id})")
        album_detail = client.get_album_detail(album_id)
        episode_list = album_detail.episode_list
        remote_count = len(episode_list)
        local_info = state.get(str(album_id), {})
        local_count = local_info.get("count", 0) if isinstance(local_info, dict) else local_info

        # 判断完结状态
        last_chapter_title = episode_list[-1][2] if episode_list else ""
        is_complete = album.get("status", "连载中") == "已完结" or "完結" in last_chapter_title or "完结" in last_chapter_title
        status_text = "已完结" if is_complete else "连载中"

        if os.path.exists(cbz):
            if remote_count <= local_count:
                print(f"已是最新: {local_count} 章 ({status_text}), 无需更新")
                return
            else:
                print(f"发现更新: 本地 {local_count} 章 → 远端 {remote_count} 章 ({status_text}), 重新下载")
                os.remove(cbz)

        print(f"开始下载: {name} ({album_id}), 共 {remote_count} 个章节 ({status_text})")

        # 下载
        jmcomic.download_album(album_id, option)

        # 散图目录: BASE_DIR/album_id/ (内含各章节子目录 photo_id/)
        source = os.path.join(BASE_DIR, str(album_id))

        if not os.path.exists(source):
            print("找不到图片目录:", source)
            return

        make_cbz(source, cbz, album, episode_list)

        print("生成:", cbz)

        # 记录章节状态
        state[str(album_id)] = {
            "count": remote_count,
            "title": last_chapter_title,
            "status": status_text
        }
        save_state(state)

        shutil.rmtree(source, ignore_errors=True)

    # ======================
    # 收藏分页
    # ======================

    page = 1
    total = 0
    seen_ids = set()

    while True:
        print("\n获取收藏页:", page)

        try:
            result = client.favorite_folder(page)
        except Exception as e:
            if "401" in str(e) or "登入" in str(e):
                print("Token过期，重新登录...")
                do_login()
                continue
            else:
                raise

        if not result.content:
            break

        page_ids = set()
        for album_id, album in result.content:
            page_ids.add(album_id)

        # 如果本页所有ID都已见过，说明到尾了
        if page_ids.issubset(seen_ids):
            print("已无新内容，结束分页")
            break

        for album_id, album in result.content:
            if album_id in seen_ids:
                continue
            seen_ids.add(album_id)
            total += 1
            try:
                download_album(album_id, album)
            except Exception as e:
                print(f"下载失败 [{album_id}]:", e)

        page += 1

    print("\n全部完成，共:", total)


if __name__ == "__main__":
    run()
