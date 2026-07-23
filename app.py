from flask import Flask, request, jsonify, render_template_string
import os
import re
import json
import sys
import threading
import contextlib
import logging
from datetime import datetime
import paths
from scripts import download as download_module
from scripts import favorite_sync as sync_module
from scripts import search as search_module

app = Flask(__name__)

IDS_FILE = str(paths.IDS_FILE)
ACCOUNT_FILE = str(paths.ACCOUNT_FILE)
STATE_FILE = str(paths.STATE_FILE)
LOG_DIR = str(paths.LOG_DIR)

tasks = {
    "download": {"thread": None, "log": os.path.join(LOG_DIR, "download.log")},
    "sync": {"thread": None, "log": os.path.join(LOG_DIR, "sync.log")},
}


# ======================
# 工具函数
# ======================

def read_lines(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    return []


def start_task(name, target):
    task = tasks[name]
    if task["thread"] and task["thread"].is_alive():
        return False, "任务正在运行中"

    def thread_wrapper():
        log_fd = open(task["log"], "w", encoding="utf-8")
        # 配置 logging 输出到日志文件（jmcomic 内部使用 logging）
        handler = logging.StreamHandler(log_fd)
        handler.setFormatter(logging.Formatter('[%(asctime)s] [%(threadName)s]:%(message)s'))
        root_logger = logging.getLogger()
        old_handlers = root_logger.handlers[:]
        old_level = root_logger.level
        root_logger.handlers = [handler]
        root_logger.setLevel(logging.INFO)
        try:
            with contextlib.redirect_stdout(log_fd), contextlib.redirect_stderr(log_fd):
                target()
        except Exception as e:
            print(f"任务异常: {e}", file=sys.stderr)
        finally:
            root_logger.handlers = old_handlers
            root_logger.setLevel(old_level)
            log_fd.close()
        task["thread"] = None

    t = threading.Thread(target=thread_wrapper, daemon=True)
    task["thread"] = t
    t.start()
    return True, "已启动"


def task_status(name):
    task = tasks[name]
    if task["thread"] and task["thread"].is_alive():
        return "running"
    return "idle"


def read_tail(path, n=300):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return "".join(lines[-n:])


# ======================
# API 路由
# ======================

@app.route("/api/queue")
def api_get_queue():
    return jsonify({"ids": read_lines(IDS_FILE)})


@app.route("/api/queue", methods=["POST"])
def api_add_queue():
    mid = (request.json.get("id") or "").strip()
    if not mid:
        return jsonify({"ok": False, "msg": "ID不能为空"}), 400
    with open(IDS_FILE, "a", encoding="utf-8") as f:
        f.write(mid + "\n")
    return jsonify({"ok": True})


@app.route("/api/queue/<item>", methods=["DELETE"])
def api_del_queue(item):
    ids = [i for i in read_lines(IDS_FILE) if i != item]
    with open(IDS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ids) + ("\n" if ids else ""))
    return jsonify({"ok": True})


@app.route("/api/queue", methods=["DELETE"])
def api_clear_queue():
    open(IDS_FILE, "w").close()
    return jsonify({"ok": True})


@app.route("/api/search", methods=["POST"])
def api_search():
    keyword = (request.json.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"results": []})
    try:
        results = search_module.search(keyword)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"results": [{"id": aid, "title": title} for aid, title in results]})


@app.route("/api/download", methods=["POST"])
def api_download():
    ok, msg = start_task("download", download_module.run)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    if not os.path.exists(ACCOUNT_FILE):
        return jsonify({"ok": False, "msg": "请先登录账号"}), 400
    ok, msg = start_task("sync", sync_module.run)
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/account", methods=["POST"])
def api_save_account():
    data = request.json
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return jsonify({"ok": False, "msg": "用户名和密码不能为空"}), 400
    with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
        f.write(username + "\n" + password + "\n")
    return jsonify({"ok": True, "msg": "登录信息已保存"})


@app.route("/api/account")
def api_get_account():
    lines = read_lines(ACCOUNT_FILE)
    saved = len(lines) >= 2
    return jsonify({
        "saved": saved,
        "username": lines[0] if saved else "",
    })


@app.route("/api/account", methods=["DELETE"])
def api_delete_account():
    if os.path.exists(ACCOUNT_FILE):
        os.remove(ACCOUNT_FILE)
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify({
        "download": task_status("download"),
        "sync": task_status("sync"),
    })


@app.route("/api/logs/<name>")
def api_logs(name):
    if name not in tasks:
        return jsonify({"error": "未知任务"}), 400
    return jsonify({"log": read_tail(tasks[name]["log"])})


@app.route("/api/done")
def api_done():
    dl_dir = str(paths.DOWNLOADS_DIR)
    done = []
    chapter_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # 向后兼容: 旧格式是纯数字
            for k, v in raw.items():
                if isinstance(v, dict):
                    chapter_state[k] = v
                else:
                    chapter_state[k] = {"count": v, "status": "连载中", "title": ""}
        except Exception:
            pass
    if os.path.isdir(dl_dir):
        for folder in os.listdir(dl_dir):
            fpath = os.path.join(dl_dir, folder)
            if not os.path.isdir(fpath):
                continue
            cbz = None
            for f in os.listdir(fpath):
                if f.lower().endswith(".cbz"):
                    cbz = os.path.join(fpath, f)
                    break
            if cbz:
                size = os.path.getsize(cbz)
                if size >= 1024 * 1024 * 1024:
                    size_str = f"{size / 1024 / 1024 / 1024:.1f} GB"
                elif size >= 1024 * 1024:
                    size_str = f"{size / 1024 / 1024:.1f} MB"
                else:
                    size_str = f"{size / 1024:.1f} KB"
                mtime = os.path.getmtime(cbz)
                time_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                done.append({"name": folder, "size": size_str, "time": time_str})
    done.sort(key=lambda x: x["name"])
    result = {"done": done, "chapter_data": chapter_state}
    return result


# ======================
# 页面
# ======================

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JMComic 下载管理</title>
<style>
/* 亮色主题 */
:root, [data-theme=light]{
  --bg:#f0f2f5; --card:#ffffff; --border:#e0e0e0;
  --text:#1a1a1a; --dim:#666; --accent:#e94560;
  --ok:#2e9e6e; --warn:#d4920a; --radius:8px;
  --input-bg:#f5f5f5; --log-bg:#f5f5f5; --log-text:#555;
}
/* 暗色主题 */
[data-theme=dark]{
  --bg:#1a1a2e; --card:#16213e; --border:#0f3460;
  --text:#e0e0e0; --dim:#888; --accent:#e94560;
  --ok:#4ecca3; --warn:#f0a500; --radius:8px;
  --input-bg:#0d1b2a; --log-bg:#0d1b2a; --log-text:#a8b8d8;
}
/* 自动跟随系统 */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --bg:#1a1a2e; --card:#16213e; --border:#0f3460;
    --text:#e0e0e0; --dim:#888; --accent:#e94560;
    --ok:#4ecca3; --warn:#f0a500; --radius:8px;
    --input-bg:#0d1b2a; --log-bg:#0d1b2a; --log-text:#a8b8d8;
  }
}
*{box-sizing:border-box; margin:0; padding:0;}
body{
  font-family:-apple-system,"Segoe UI",Roboto,"Microsoft YaHei",sans-serif;
  background:var(--bg); color:var(--text); line-height:1.6; padding:20px;
  max-width:900px; margin:0 auto; transition:background .3s, color .3s;
}
h1{font-size:1.5rem; margin-bottom:24px; display:flex; align-items:center; justify-content:space-between;}
h2{font-size:1rem; margin-bottom:10px; color:var(--dim); display:flex; align-items:center; gap:8px;}
h2 .dot{width:8px;height:8px;border-radius:50%;display:inline-block;}
h2 .dot-running{background:var(--warn);animation:pulse 1.5s infinite;}
h2 .dot-idle{background:var(--dim); opacity:.3;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
.card{
  background:var(--card); border:1px solid var(--border);
  border-radius:var(--radius); padding:20px; margin-bottom:20px;
  transition:background .3s, border-color .3s;
}
.row{display:flex; gap:10px; flex-wrap:wrap; align-items:center;}
input[type=text],input[type=password]{
  flex:1; min-width:180px; padding:10px 14px; border-radius:var(--radius);
  border:1px solid var(--border); background:var(--input-bg); color:var(--text);
  font-size:14px; transition:background .3s, border-color .3s, color .3s;
}
input:focus{outline:none; border-color:var(--accent);}
button{
  padding:10px 18px; border-radius:var(--radius); border:none;
  cursor:pointer; font-size:14px; transition:.15s; white-space:nowrap;
}
.btn-primary{background:var(--accent); color:#fff;}
.btn-primary:hover{opacity:.85;}
.btn-sm{padding:5px 12px; font-size:12px;}
.btn-danger{background:#c0392b; color:#fff;}
.btn-ok{background:var(--ok); color:#fff;}
.btn-warn{background:var(--warn); color:#000;}
.btn-ghost{background:transparent; border:1px solid var(--border); color:var(--dim); font-size:12px;}
.btn-ghost:hover{color:var(--text); border-color:var(--accent);}
.result-item,.queue-item,.done-item{
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 0; border-bottom:1px solid var(--border); gap:10px;
}
.result-item:last-child,.queue-item:last-child,.done-item:last-child{border-bottom:none;}
.result-title{flex:1; word-break:break-all; font-size:14px;}
.result-id{color:var(--dim); font-size:12px; min-width:60px; text-align:right;}
.queue-id{font-family:monospace; flex:1; font-size:13px;}
.done-name{flex:1; word-break:break-all; font-size:13px;}
.done-meta{color:var(--dim); font-size:12px; display:flex; gap:14px; flex-shrink:0; align-items:center;}
.done-status{padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold; white-space:nowrap;}
.status-done{background:var(--ok); color:#fff;}
.status-ongoing{background:var(--warn); color:#000;}
.empty{color:var(--dim); text-align:center; padding:16px; font-size:13px;}
.log-box{
  background:var(--log-bg); border-radius:var(--radius); padding:12px;
  font-family:Consolas,"Courier New",monospace; font-size:12px; max-height:300px;
  overflow-y:auto; white-space:pre-wrap; word-break:break-all;
  color:var(--log-text); line-height:1.5; margin-top:12px;
  transition:background .3s, color .3s;
}
.toast{
  position:fixed; top:20px; right:20px; z-index:9999;
  padding:14px 22px; border-radius:var(--radius); font-size:14px;
  animation:slideIn .3s; box-shadow:0 4px 12px rgba(0,0,0,.4);
}
.toast-ok{background:var(--ok); color:#fff;}
.toast-err{background:var(--accent); color:#fff;}
@keyframes slideIn{from{transform:translateX(120%);} to{transform:translateX(0);}}
.badge{
  display:inline-block; padding:2px 10px; border-radius:12px;
  font-size:11px; font-weight:bold; vertical-align:middle;
}
.badge-running{background:var(--warn); color:#000;}
.badge-saved{background:var(--ok); color:#fff;}
.account-row{display:flex; gap:10px; align-items:end;}
.account-row .field{flex:1; display:flex; flex-direction:column; gap:4px;}
.account-row label{font-size:12px; color:var(--dim);}
.section-gap{height:1px; background:var(--border); margin:14px 0;}
.theme-btn{
  background:transparent; border:1px solid var(--border); color:var(--dim);
  padding:6px 12px; font-size:18px; cursor:pointer; border-radius:var(--radius);
  line-height:1; transition:.15s;
}
.theme-btn:hover{border-color:var(--accent); color:var(--text);}
</style>
</head>
<body>

<h1>
  <span>JMComic 下载管理</span>
  <button class="theme-btn" onclick="toggleTheme()" title="切换主题" id="themeBtn">&#9790;</button>
</h1>

<!-- 同步收藏 -->
<div class="card">
  <h2>同步收藏 <span id="syncStatus" class="badge badge-idle" style="display:none;"></span>
    <span id="accountBadge" class="badge badge-saved" style="display:none;"></span></h2>

  <div class="account-row" id="accountForm" style="display:none;">
    <div class="field">
      <label>用户名</label>
      <input type="text" id="accUser" placeholder="JM账号">
    </div>
    <div class="field">
      <label>密码</label>
      <input type="password" id="accPass" placeholder="密码">
    </div>
    <button class="btn-primary btn-sm" onclick="saveAccount()">保存</button>
  </div>
  <div class="account-row" id="accountInfo" style="display:none;">
    <span style="flex:1;font-size:14px;">已登录: <strong id="accountName"></strong></span>
    <button class="btn-danger btn-sm" onclick="logoutAccount()">退出登录</button>
  </div>

  <div class="section-gap"></div>

  <div class="row">
    <button class="btn-warn" id="btnSync" onclick="startSync()">同步收藏</button>
    <div style="flex:1"></div>
    <button class="btn-ghost" onclick="toggleLog('sync')">
      <span id="logToggleSync">展开日志</span>
    </button>
  </div>
  <div class="log-box" id="logSync" style="display:none;">暂无日志</div>
</div>

<!-- 搜索漫画 -->
<div class="card">
  <h2>搜索漫画</h2>
  <div class="row">
    <input type="text" id="keyword" placeholder="输入关键词" onkeydown="if(event.key==='Enter')doSearch()">
    <button class="btn-primary" onclick="doSearch()">搜索</button>
  </div>
  <div id="searchResults"></div>
</div>

<!-- 下载队列 -->
<div class="card">
  <h2>下载队列 <span id="dlStatus" class="badge badge-idle" style="display:none;"></span>
    <span id="queueCount" style="color:var(--dim);font-weight:normal;font-size:13px;"></span></h2>
  <div class="row" style="margin-bottom:10px;">
    <input type="text" id="manualId" placeholder="手动输入漫画ID" onkeydown="if(event.key==='Enter')addManual()">
    <button class="btn-primary btn-sm" onclick="addManual()">加入</button>
  </div>
  <div id="queueList"></div>
  <div class="row" style="margin-top:14px;">
    <button class="btn-ok" id="btnDownload" onclick="startDownload()">开始下载</button>
    <button class="btn-danger" onclick="clearQueue()">清空队列</button>
    <div style="flex:1"></div>
    <button class="btn-ghost" onclick="toggleLog('download')">
      <span id="logToggleDownload">展开日志</span>
    </button>
  </div>
  <div class="log-box" id="logDownload" style="display:none;">暂无日志</div>
</div>

<!-- 已完成 -->
<div class="card">
  <h2>已完成 <span id="doneCount" style="color:var(--dim);font-weight:normal;font-size:13px;"></span></h2>
  <div id="doneList"></div>
</div>

<div style="text-align:center;color:var(--dim);font-size:12px;padding:8px 0 20px;line-height:2;">
  <strong style="color:var(--text);">JMComic Downloader</strong> &mdash; 禁漫天堂漫画下载工具<br>
  输出格式: CBZ (含 ComicInfo.xml 元数据)，兼容 Komga / Kavita / Mihon / LANraragi 等阅读器<br>
  Docker 部署时将下载目录 <code style="background:var(--card);padding:2px 6px;border-radius:4px;">/downloads</code> 挂载为持久卷，即可被阅读器直接扫描识别<br>
  同步收藏功能需要登录 JM 账号，账号信息仅保存在本地服务器，不会上传至任何第三方
</div>

<script>
const logVisible={download:false, sync:false};
let pollTimer=null;

// === 主题 ===
function initTheme(){
  const saved=localStorage.getItem('theme');
  if(saved==='light'||saved==='dark'){
    document.documentElement.setAttribute('data-theme',saved);
  }
  updateThemeIcon();
}

function getTheme(){
  const s=document.documentElement.getAttribute('data-theme');
  if(s) return s;
  return window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
}

function toggleTheme(){
  const cur=getTheme();
  const next=cur==='dark'?'light':'dark';
  if(next==='light'||next==='dark'){
    document.documentElement.setAttribute('data-theme',next);
    localStorage.setItem('theme',next);
  }else{
    document.documentElement.removeAttribute('data-theme');
    localStorage.removeItem('theme');
  }
  updateThemeIcon();
}

function updateThemeIcon(){
  document.getElementById('themeBtn').innerHTML=getTheme()==='dark'?'&#9728;':'&#9790;';
}

initTheme();
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',()=>{
  if(!localStorage.getItem('theme')) updateThemeIcon();
});

// === 工具 ===
function toast(msg,ok=true){
  const t=document.createElement('div');
  t.className='toast '+(ok?'toast-ok':'toast-err');
  t.textContent=msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),3000);
}

async function api(url,method='GET',body=null){
  const opt={method,headers:{}};
  if(body){opt.headers['Content-Type']='application/json'; opt.body=JSON.stringify(body);}
  const r=await fetch(url,opt);
  return r.json();
}

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

// === 搜索 ===
async function doSearch(){
  const kw=document.getElementById('keyword').value.trim();
  if(!kw)return;
  const box=document.getElementById('searchResults');
  box.innerHTML='<div class="empty">搜索中...</div>';
  try{
    const data=await api('/api/search','POST',{keyword:kw});
    if(data.error){box.innerHTML=''; toast(data.error,false); return;}
    if(!data.results.length){box.innerHTML='<div class="empty">无结果</div>'; return;}
    box.innerHTML=data.results.map(r=>`
      <div class="result-item">
        <span class="result-title">${esc(r.title)}</span>
        <span class="result-id">${r.id}</span>
        <button class="btn-primary btn-sm" onclick="addQueue('${r.id}')">加入</button>
      </div>`).join('');
  }catch(e){box.innerHTML=''; toast('搜索失败',false);}
}

// === 队列 ===
async function loadQueue(){
  const data=await api('/api/queue');
  const list=document.getElementById('queueList');
  document.getElementById('queueCount').textContent=data.ids.length?'('+data.ids.length+')':'';
  if(!data.ids.length){list.innerHTML='<div class="empty">队列为空</div>'; return;}
  list.innerHTML=data.ids.map(id=>`
    <div class="queue-item">
      <span class="queue-id">${id}</span>
      <button class="btn-danger btn-sm" onclick="delQueue('${id}')">删除</button>
    </div>`).join('');
}

async function addQueue(id){
  await api('/api/queue','POST',{id});
  toast('已加入队列');
  loadQueue();
}

async function addManual(){
  const id=document.getElementById('manualId').value.trim();
  if(!id)return;
  await api('/api/queue','POST',{id});
  document.getElementById('manualId').value='';
  toast('已加入队列');
  loadQueue();
}

async function delQueue(id){
  await api('/api/queue/'+id,'DELETE');
  loadQueue();
}

async function clearQueue(){
  if(!confirm('确定清空队列?'))return;
  await api('/api/queue','DELETE');
  toast('已清空');
  loadQueue();
}

// === 账号 ===
async function loadAccount(){
  const data=await api('/api/account');
  const badge=document.getElementById('accountBadge');
  const form=document.getElementById('accountForm');
  const info=document.getElementById('accountInfo');
  if(data.saved){
    badge.style.display='';
    badge.textContent=data.username;
    form.style.display='none';
    info.style.display='';
    document.getElementById('accountName').textContent=data.username;
  }else{
    badge.style.display='none';
    form.style.display='';
    info.style.display='none';
  }
}

async function saveAccount(){
  const u=document.getElementById('accUser').value.trim();
  const p=document.getElementById('accPass').value.trim();
  if(!u||!p){toast('请输入用户名和密码',false); return;}
  const data=await api('/api/account','POST',{username:u,password:p});
  toast(data.msg, data.ok);
  if(data.ok){document.getElementById('accPass').value=''; loadAccount();}
}

async function logoutAccount(){
  await api('/api/account','DELETE');
  toast('已退出登录');
  loadAccount();
}

// === 任务 ===
async function startDownload(){
  const data=await api('/api/download','POST');
  toast(data.msg, data.ok);
  if(data.ok) ensurePoll();
}

async function startSync(){
  const data=await api('/api/sync','POST');
  toast(data.msg, data.ok);
  if(data.ok) ensurePoll();
}

// === 状态 ===
async function loadStatus(){
  const data=await api('/api/status');
  updateTaskUI('download', data.download);
  updateTaskUI('sync', data.sync);
  if(data.download==='running'||data.sync==='running') ensurePoll();
  else stopPoll();
}

function updateTaskUI(name, status){
  const running=status==='running';
  const badgeId = name==='download'?'dlStatus':'syncStatus';
  const btnId = name==='download'?'btnDownload':'btnSync';
  const el=document.getElementById(badgeId);
  if(running){
    el.style.display='';
    el.className='badge badge-running';
    el.textContent='运行中';
  }else{
    el.style.display='none';
  }
  const btn=document.getElementById(btnId);
  btn.disabled=running;
  btn.style.opacity=running?.5:1;
}

// === 日志 ===
function toggleLog(name){
  const box=document.getElementById('log'+name.charAt(0).toUpperCase()+name.slice(1));
  const toggle=document.getElementById('logToggle'+name.charAt(0).toUpperCase()+name.slice(1));
  logVisible[name]=!logVisible[name];
  box.style.display=logVisible[name]?'':'none';
  toggle.textContent=logVisible[name]?'收起日志':'展开日志';
  if(logVisible[name]) loadLog(name);
}

async function loadLog(name){
  const data=await api('/api/logs/'+name);
  const id='log'+name.charAt(0).toUpperCase()+name.slice(1);
  const box=document.getElementById(id);
  box.textContent=data.log||'暂无日志';
  box.scrollTop=box.scrollHeight;
}

function ensurePoll(){
  if(pollTimer) return;
  pollTimer=setInterval(async()=>{
    const s=await api('/api/status');
    loadStatus();
    ['download','sync'].forEach(n=>{
      if(logVisible[n]) loadLog(n);
    });
    if(s.download!=='running'&&s.sync!=='running'){
      stopPoll();
      loadQueue(); loadDone();
    }
  },2000);
}

function stopPoll(){
  if(pollTimer){clearInterval(pollTimer); pollTimer=null;}
}

// === 完成 ===
function getAlbumId(name){
  const m=name.match(/\((\d+)\)$/);
  return m?m[1]:'';
}

async function loadDone(){
  const data=await api('/api/done');
  const state=data.chapter_data||{};
  document.getElementById('doneCount').textContent=data.done.length?'('+data.done.length+')':'';
  const list=document.getElementById('doneList');
  if(!data.done.length){list.innerHTML='<div class="empty">无记录</div>'; return;}
  list.innerHTML=data.done.map(item=>{
    const aid=getAlbumId(item.name);
    const info=state[aid]||{};
    const status=info.status||'连载中';
    const count=info.count||'?';
    const statusClass=status==='已完结'?'status-done':'status-ongoing';
    return `
    <div class="done-item">
      <span class="done-name">${esc(item.name)}</span>
      <span class="done-meta">
        <span class="done-status ${statusClass}">${status}</span>
        <span>已下${count}话</span>
        <span>${item.size}</span>
        <span>${item.time}</span>
      </span>
    </div>`;
  }).join('');
}

// === 初始化 ===
loadQueue(); loadDone(); loadAccount(); loadStatus();
setInterval(loadStatus,5000);
</script>

</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)