# JMComic Downloader

一个简洁美观的禁漫天堂漫画下载管理器，支持 Docker / Windows / macOS 三端部署。

## 功能特性

- 漫画搜索与下载（CBZ 格式，含 ComicInfo.xml 元数据）
- 收藏同步（需登录 JM 账号）
- 下载队列管理
- 实时日志查看
- 已完成列表（显示大小、时间、完结状态）
- 深色/亮色主题自动切换
- 响应式设计，支持移动端访问

## 部署方式

### 方式一：Docker（推荐用于 NAS）

```bash
docker build -t jmcomic-web .
docker run -d -p 8080:8080 -v /path/to/downloads:/downloads jmcomic-web
```

unraid 等 NAS 系统可在 Docker 模板中配置：
- 端口映射：`8080:8080`
- 数据卷：`/downloads` 映射到你的漫画库目录

### 方式二：Windows 本地运行

**便携版 exe：**

下载 [dist/JMComic-Web.exe](dist/JMComic-Web.exe)，双击运行即可。
- 数据文件（ids.txt、account.txt、logs 等）自动生成在 exe 同级目录
- 下载目录：`exe所在目录/downloads/`

**源码运行：**

```bash
pip install -r requirements.txt
python app.py
```

访问 http://localhost:8080

### 方式三：macOS

** dmg 包：**（待构建）

数据目录：`~/.jmcomic-web/`
下载目录：`~/Downloads/jmcomic-web/`

## 使用说明

### 搜索漫画

在"搜索漫画"输入框输入关键词，点击搜索，结果列表可一键加入队列。

### 手动添加

在"下载队列"输入漫画 ID（如 `123456`），点击"加入"。

### 同步收藏

1. 在"同步收藏"区域填写 JM 账号用户名和密码，点击保存
2. 点击"同步收藏"，程序会自动下载你的收藏夹漫画
3. 账号信息仅保存在本地，不会上传任何第三方

### 下载队列

- 点击"开始下载"执行队列中的所有任务
- 点击"清空队列"清除未下载的任务
- 可展开日志查看实时下载进度

### 已完成

显示已下载的漫画（CBZ 文件），包含：
- 文件大小
- 下载时间
- 完结状态（连载中/已完结）
- 已下载话数

## 输出格式

CBZ 文件结构：

```
漫画名 (ID)/
├── 漫画名 (ID).cbz    # CBZ 压缩包，含 ComicInfo.xml 元数据
└── 001.jpg            # 原始图片（下载时自动删除，仅保留 cbz）
```

兼容阅读器：Komga / Kavita / Mihon / LANraragi 等。

## 目录结构

```
.
├── app.py              # Flask 主程序
├── paths.py            # 统一路径管理（三端自适应）
├── config.yml          # jmcomic 配置（已由 paths.py 动态生成）
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 构建文件
├── build_exe.py        # Windows exe 打包脚本
├── scripts/
│   ├── download.py     # 下载核心逻辑
│   ├── favorite_sync.py # 收藏同步逻辑
│   ├── search.py       # 搜索逻辑
│   └── pack_cbz.py     # CBZ 打包逻辑
└── templates/          # （无，HTML 内嵌在 app.py）
```

## 数据文件

| 文件 | 说明 |
|------|------|
| ids.txt | 下载队列（每行一个漫画 ID） |
| account.txt | JM 账号（用户名 + 密码，各一行） |
| state.json | 下载状态（漫画 ID → 已下载话数、完结状态等） |
| logs/download.log | 下载日志 |
| logs/sync.log | 同步日志 |

## 开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行开发服务器
python app.py

# 打包 Windows exe
python build_exe.py
```

## 许可证

MIT License

## 免责声明

本项目仅供学习交流使用，请勿用于商业用途。下载的漫画内容版权归原作者所有，使用本工具下载即表示您同意自行承担相关法律责任。

---

**JMComic Downloader** - 简洁高效的漫画下载管理工具
