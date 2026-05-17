# app.py - نظام استضافة متكامل مع دعم البريد الإلكتروني والألوان الذهبية - نسخة محدثة بالكامل
import os
import json
import re
import subprocess
import psutil
import socket
import sys
import hashlib
import secrets
import time
import threading
import requests
import shutil
import zipfile
import signal
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request, jsonify, session, redirect, make_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "USERS")
os.makedirs(USERS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)
app.secret_key = "LORD_HOST_GOLD_2026_SECRET_KEY_ULTRA"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ============== بيانات المسؤول ==============
ADMIN_EMAIL = "admin@ziadhost.com"
ADMIN_PASSWORD_RAW = "admin123"

# ============== إعدادات البوت والإشعارات ==============
BOT_TOKEN = "8715602644:AAHbyHwAtehq4K-iYHMTJI5RyxGdOdd3Q1Q"
ADMIN_TELEGRAM_ID = 8539487894

def notify_admin(message: str):
    """إرسال إشعار للأدمن على تليجرام"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_TELEGRAM_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception:
        pass

# ============== قاعدة البيانات ==============
DB_FILE = os.path.join(BASE_DIR, "db.json")

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "plans" not in data:
                    data["plans"] = {}
                return data
        except Exception:
            pass
    admin_hash = hashlib.sha256(ADMIN_PASSWORD_RAW.encode()).hexdigest()
    default_db = {
        "users": {
            ADMIN_EMAIL: {
                "password": admin_hash,
                "is_admin": True,
                "created_at": str(datetime.now()),
                "max_servers": 999999,
                "expiry_days": 3650,
                "last_login": None,
                "telegram_id": None,
                "api_key": None,
                "storage_limit": 10240000,
                "plan": "admin"
            }
        },
        "servers": {},
        "logs": [],
        "plans": {
            "basic": {"name": "🌟 خطة أساسية", "storage": 102400, "ram": 512, "cpu": 0.5, "max_servers": 5, "price": 0},
            "premium": {"name": "💎 خطة احترافية", "storage": 512000, "ram": 2048, "cpu": 1.5, "max_servers": 15, "price": 9.99},
            "ultimate": {"name": "👑 خطة أسطورية", "storage": 2048000, "ram": 8192, "cpu": 4, "max_servers": 30, "price": 24.99}
        }
    }
    save_db(default_db)
    return default_db

def save_db(db_data):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ DB: {e}")
        return False

db = load_db()

# ============== المنافذ ==============
PORT_RANGE_START = 8100
PORT_RANGE_END = 9100

def get_assigned_port():
    used = set()
    for srv in db.get("servers", {}).values():
        if srv.get("port"):
            used.add(srv["port"])
    for port in range(PORT_RANGE_START, PORT_RANGE_END):
        if port not in used:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.1)
                result = s.connect_ex(('127.0.0.1', port))
                s.close()
                if result != 0:
                    return port
            except Exception:
                return port
    return PORT_RANGE_START

# ============== دوال مساعدة ==============
def get_current_user():
    if "email" in session:
        return db["users"].get(session["email"])
    return None

def get_user_servers_dir(email):
    safe_email = email.replace('@', '_at_').replace('.', '_dot_')
    path = os.path.join(USERS_DIR, safe_email, "SERVERS")
    os.makedirs(path, exist_ok=True)
    return path

def is_admin(email):
    if email == ADMIN_EMAIL:
        return True
    u = db["users"].get(email)
    return u.get("is_admin", False) if u else False

def get_public_ip():
    try:
        return requests.get('https://api.ipify.org', timeout=3).text
    except Exception:
        return "127.0.0.1"

def generate_api_key():
    return secrets.token_urlsafe(32)

def get_user_by_api_key(api_key):
    for email, udata in db["users"].items():
        if udata.get("api_key") == api_key:
            return email, udata
    return None, None

def uptime_str(start_time):
    if not start_time:
        return "0 ثانية"
    diff = time.time() - start_time
    days = int(diff // 86400)
    hours = int((diff % 86400) // 3600)
    mins = int((diff % 3600) // 60)
    parts = []
    if days > 0: parts.append(f"{days} يوم")
    if hours > 0: parts.append(f"{hours} ساعة")
    if mins > 0: parts.append(f"{mins} دقيقة")
    return " و ".join(parts) if parts else "أقل من دقيقة"

def _check_admin_access():
    if "email" in session and is_admin(session["email"]):
        return True
    api_key = None
    if request.is_json:
        try:
            api_key = request.get_json().get("api_key")
        except Exception:
            pass
    if not api_key:
        api_key = request.args.get("api_key")
    if api_key:
        email, user = get_user_by_api_key(api_key)
        if email and is_admin(email):
            return True
    return False

# ============== تشغيل السيرفر ==============
def detect_main_file(srv_path: str) -> str:
    for candidate in ["main.py", "bot.py", "app.py", "index.py", "run.py", "start.py"]:
        if os.path.exists(os.path.join(srv_path, candidate)):
            return candidate
    py_files = [f for f in os.listdir(srv_path) if f.endswith('.py')]
    return py_files[0] if py_files else ""

def auto_install_deps(srv_path: str, log_file):
    try:
        req = os.path.join(srv_path, "requirements.txt")
        if os.path.exists(req):
            log_file.write(f"\n📦 تثبيت requirements.txt...\n")
            log_file.flush()
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=srv_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy()
            )
            proc.wait(timeout=180)
            log_file.write("✅ تم تثبيت المكتبات\n")
    except Exception as e:
        log_file.write(f"\n⚠️ تثبيت تلقائي: {e}\n")
    log_file.flush()

def start_server_process(folder):
    srv = db["servers"].get(folder)
    if not srv:
        return False, "السيرفر غير موجود"

    main_file = srv.get("startup_file", "")
    if not main_file:
        main_file = detect_main_file(srv["path"])
        if main_file:
            srv["startup_file"] = main_file
            save_db(db)
        else:
            return False, "لا يوجد ملف تشغيل Python (.py)"

    file_path = os.path.join(srv["path"], main_file)
    if not os.path.exists(file_path):
        return False, f"الملف '{main_file}' غير موجود"

    port = srv.get("port") or get_assigned_port()
    srv["port"] = port
    save_db(db)

    log_path = os.path.join(srv["path"], "out.log")
    error_path = os.path.join(srv["path"], "errors.log")
    log_file = open(log_path, "a", encoding='utf-8')
    log_file.write(
        f"\n{'='*50}\n🚀 بدء التشغيل - {datetime.now()}\n"
        f"📁 {main_file}\n🔌 المنفذ: {port}\n🏷 النوع: Python\n{'='*50}\n\n"
    )
    log_file.flush()

    try:
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["SERVER_PORT"] = str(port)
        cmd = [sys.executable, "-u", main_file]
        proc = subprocess.Popen(
            cmd,
            cwd=srv["path"],
            stdout=log_file,
            stderr=open(error_path, "a", encoding='utf-8'),
            env=env,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )
        srv["status"] = "Running"
        srv["pid"] = proc.pid
        srv["start_time"] = time.time()
        save_db(db)
        return True, "✅ تم التشغيل"
    except FileNotFoundError:
        err = "❌ Python غير موجود"
        log_file.write(err + "\n")
        log_file.close()
        return False, err
    except Exception as e:
        log_file.write(f"\n❌ خطأ: {e}\n")
        log_file.close()
        return False, str(e)

def stop_server_process(folder):
    srv = db["servers"].get(folder)
    if not srv:
        return
    if srv.get("pid"):
        try:
            p = psutil.Process(srv["pid"])
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                except Exception:
                    pass
            for child in p.children(recursive=True):
                child.kill()
            p.kill()
        except Exception:
            pass
    srv["status"] = "Stopped"
    srv["pid"] = None
    save_db(db)

def restart_server(folder):
    stop_server_process(folder)
    time.sleep(2)
    start_server_process(folder)

# ============== مراقبة العمليات ==============
def process_monitor():
    while True:
        try:
            for folder, srv in list(db["servers"].items()):
                if srv.get("status") == "Running" and srv.get("pid"):
                    try:
                        p = psutil.Process(srv["pid"])
                        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                            restart_server(folder)
                    except psutil.NoSuchProcess:
                        restart_server(folder)
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(15)

threading.Thread(target=process_monitor, daemon=True).start()

# ============== الصفحات ==============
@app.route('/')
def home():
    if 'email' in session:
        if is_admin(session['email']):
            return redirect('/admin')
        return redirect('/dashboard')
    return redirect('/welcome')

@app.route('/welcome')
def welcome_page():
    return send_from_directory(BASE_DIR, 'landing.html')

@app.route('/login')
def login_page():
    if 'email' in session:
        return redirect('/')
    return send_from_directory(BASE_DIR, 'login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect('/login')
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/admin')
def admin_panel():
    if 'email' not in session or not is_admin(session['email']):
        return redirect('/login')
    return send_from_directory(BASE_DIR, 'admin_panel.html')

# ============== API المصادقة ==============
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    
    if not email or not password:
        return jsonify({"success": False, "message": "جميع الحقول مطلوبة"})
    if '@' not in email or '.' not in email:
        return jsonify({"success": False, "message": "البريد الإلكتروني غير صالح"})
    if len(password) < 4:
        return jsonify({"success": False, "message": "كلمة المرور 4 أحرف على الأقل"})
    if email in db["users"]:
        return jsonify({"success": False, "message": "البريد الإلكتروني موجود بالفعل"})
    if email == ADMIN_EMAIL:
        return jsonify({"success": False, "message": "لا يمكن استخدام هذا البريد"})

    db["users"][email] = {
        "password": hashlib.sha256(password.encode()).hexdigest(),
        "is_admin": False,
        "created_at": str(datetime.now()),
        "max_servers": db["plans"]["basic"]["max_servers"],
        "expiry_days": 365,
        "last_login": None,
        "telegram_id": None,
        "api_key": None,
        "storage_limit": db["plans"]["basic"]["storage"],
        "plan": "basic"
    }
    save_db(db)
    
    safe_email = email.replace('@', '_at_').replace('.', '_dot_')
    user_dir = os.path.join(USERS_DIR, safe_email)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, "SERVERS"), exist_ok=True)

    threading.Thread(
        target=notify_admin,
        args=(
            f"🔔 *مستخدم جديد اشترك في LORD HOST!*\n"
            f"📧 البريد: `{email}`\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ),
        daemon=True
    ).start()

    return jsonify({
        "success": True,
        "message": f"✅ تم إنشاء حسابك بنجاح! يمكنك تسجيل الدخول الآن."
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD_RAW:
        session.clear()
        session['email'] = email
        session.permanent = True
        db["users"][ADMIN_EMAIL]["last_login"] = str(datetime.now())
        save_db(db)
        return jsonify({"success": True, "redirect": "/admin", "is_admin": True})

    user = db["users"].get(email)
    if user and user["password"] == hashlib.sha256(password.encode()).hexdigest():
        session.clear()
        session['email'] = email
        session.permanent = True
        user["last_login"] = str(datetime.now())
        save_db(db)
        return jsonify({"success": True, "redirect": "/dashboard", "is_admin": False})

    return jsonify({"success": False, "message": "بيانات غير صحيحة"})

@app.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    session.clear()
    response = make_response(jsonify({"success": True}))
    response.set_cookie('session', '', expires=0)
    return response

@app.route('/api/current_user')
def api_current_user():
    if "email" in session:
        u = db["users"].get(session["email"])
        if u:
            return jsonify({
                "success": True,
                "email": session["email"],
                "is_admin": u.get("is_admin", False) or session["email"] == ADMIN_EMAIL,
                "plan": u.get("plan", "basic")
            })
    return jsonify({"success": False})

# ============== API Key ==============
@app.route('/api/create_api_key', methods=['POST'])
def create_api_key():
    if 'email' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    email = session['email']
    new_key = generate_api_key()
    db["users"][email]["api_key"] = new_key
    save_db(db)
    return jsonify({"success": True, "api_key": new_key, "message": "تم إنشاء مفتاح API"})

@app.route('/api/link_telegram', methods=['POST'])
def link_telegram():
    if 'email' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    data = request.get_json()
    tg_id = str(data.get('telegram_id', ''))
    if not tg_id:
        return jsonify({"success": False, "message": "معرف تليجرام مطلوب"})
    db["users"][session['email']]["telegram_id"] = tg_id
    save_db(db)
    return jsonify({"success": True, "message": "تم ربط حساب التليجرام"})

# ============== API الخطط ==============
@app.route('/api/plans')
def get_plans():
    return jsonify({"success": True, "plans": db.get("plans", {})})

@app.route('/api/user/upgrade', methods=['POST'])
def upgrade_plan():
    if 'email' not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    data = request.get_json()
    plan_id = data.get("plan_id")
    if not plan_id or plan_id not in db.get("plans", {}):
        return jsonify({"success": False, "message": "خطة غير موجودة"})
    
    plan = db["plans"][plan_id]
    email = session['email']
    user = db["users"][email]
    
    user["plan"] = plan_id
    user["max_servers"] = plan["max_servers"]
    user["storage_limit"] = plan["storage"]
    
    save_db(db)
    
    threading.Thread(
        target=notify_admin,
        args=(
            f"💎 *ترقية خطة جديدة!*\n"
            f"📧 البريد: `{email}`\n"
            f"📦 الخطة: {plan['name']}\n"
            f"💰 السعر: {plan['price']}$",
        ),
        daemon=True
    ).start()
    
    return jsonify({"success": True, "message": f"✅ تم ترقية حسابك إلى {plan['name']}"})

# ============== API الإدارة - المستخدمون ==============
@app.route('/api/admin/users')
def admin_users():
    if not _check_admin_access():
        return jsonify({"success": False}), 403
    users_list = []
    for uemail, udata in db["users"].items():
        users_list.append({
            "username": uemail,
            "email": uemail,
            "is_admin": udata.get("is_admin", False),
            "created_at": udata.get("created_at"),
            "last_login": udata.get("last_login"),
            "max_servers": udata.get("max_servers", 1),
            "expiry_days": udata.get("expiry_days", 365),
            "telegram_id": udata.get("telegram_id"),
            "api_key": udata.get("api_key"),
            "plan": udata.get("plan", "basic")
        })
    return jsonify({"success": True, "users": users_list})

@app.route('/api/admin/create-user', methods=['POST'])
def admin_create_user():
    if not _check_admin_access():
        return jsonify({"success": False}), 403
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    max_servers = int(data.get("max_servers", 5))
    expiry_days = int(data.get("expiry_days", 365))
    
    if not email or not password:
        return jsonify({"success": False, "message": "جميع الحقول مطلوبة"})
    if '@' not in email:
        return jsonify({"success": False, "message": "البريد الإلكتروني غير صالح"})
    if email in db["users"]:
        return jsonify({"success": False, "message": "المستخدم موجود"})
    
    db["users"][email] = {
        "password": hashlib.sha256(password.encode()).hexdigest(),
        "is_admin": False,
        "created_at": str(datetime.now()),
        "max_servers": max_servers,
        "expiry_days": expiry_days,
        "last_login": None,
        "telegram_id": None,
        "api_key": None,
        "storage_limit": 102400,
        "plan": "basic"
    }
    save_db(db)
    
    safe_email = email.replace('@', '_at_').replace('.', '_dot_')
    user_dir = os.path.join(USERS_DIR, safe_email)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, "SERVERS"), exist_ok=True)
    
    return jsonify({"success": True, "message": "✅ تم إنشاء الحساب"})

@app.route('/api/admin/delete-user', methods=['POST'])
def admin_delete_user():
    if not _check_admin_access():
        return jsonify({"success": False}), 403
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    if not email or email == ADMIN_EMAIL:
        return jsonify({"success": False, "message": "لا يمكن حذف هذا المستخدم"})
    if email in db["users"]:
        for fid in [fid for fid, srv in db["servers"].items() if srv["owner"] == email]:
            stop_server_process(fid)
            if os.path.exists(db["servers"][fid]["path"]):
                shutil.rmtree(db["servers"][fid]["path"], ignore_errors=True)
            del db["servers"][fid]
        
        safe_email = email.replace('@', '_at_').replace('.', '_dot_')
        user_dir = os.path.join(USERS_DIR, safe_email)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir, ignore_errors=True)
        del db["users"][email]
        save_db(db)
        return jsonify({"success": True, "message": f"🗑 تم حذف المستخدم {email}"})
    return jsonify({"success": False, "message": "المستخدم غير موجود"})

@app.route('/api/admin/update-user', methods=['POST'])
def admin_update_user():
    if not _check_admin_access():
        return jsonify({"success": False}), 403
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    if email not in db["users"]:
        return jsonify({"success": False, "message": "المستخدم غير موجود"})
    u = db["users"][email]
    if "max_servers" in data:
        u["max_servers"] = int(data["max_servers"])
    if "expiry_days" in data:
        u["expiry_days"] = int(data["expiry_days"])
    if "is_admin" in data:
        u["is_admin"] = bool(data["is_admin"])
    if "storage_limit" in data:
        u["storage_limit"] = int(data["storage_limit"])
    save_db(db)
    return jsonify({"success": True, "message": f"✅ تم تحديث {email}"})

@app.route('/api/admin/add-plan', methods=['POST'])
def admin_add_plan():
    if not _check_admin_access():
        return jsonify({"success": False}), 403
    data = request.get_json()
    plan_id = data.get("plan_id") or data.get("name", "").lower().replace(" ", "_")
    if plan_id in db["plans"]:
        return jsonify({"success": False, "message": "الخطة موجودة بالفعل"})
    db["plans"][plan_id] = {
        "name": data.get("name"),
        "price": float(data.get("price", 0)),
        "storage": int(data.get("storage", 512000)),
        "ram": int(data.get("ram", 512)),
        "cpu": float(data.get("cpu", 0.5)),
        "max_servers": int(data.get("max_servers", 5))
    }
    save_db(db)
    return jsonify({"success": True, "message": "✅ تم إضافة الخطة"})

# ============== API النظام ==============
@app.route('/api/system/metrics')
def get_metrics():
    return jsonify({
        "cpu": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent
    })

@app.route('/api/ping', methods=['GET', 'POST'])
def ping():
    return jsonify({"status": "pong", "timestamp": str(datetime.now())})

# ============== السيرفرات ==============
@app.route('/api/servers')
def list_servers():
    if "email" not in session:
        return jsonify({"success": False}), 401
    
    user_servers = []
    total_disk_used_mb = 0.0
    for folder, srv in db["servers"].items():
        if srv["owner"] == session["email"]:
            disk_used = 0
            if os.path.exists(srv["path"]):
                try:
                    for root, dirs, files in os.walk(srv["path"]):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                disk_used += os.path.getsize(fp)
                            except Exception:
                                pass
                except Exception:
                    pass
            disk_used_mb = round(disk_used / (1024 * 1024), 2)
            total_disk_used_mb += disk_used_mb
            user_servers.append({
                "folder": folder,
                "title": srv["name"],
                "subtitle": "سيرفر Python",
                "type": "Python",
                "startup_file": srv.get("startup_file", ""),
                "status": srv.get("status", "Stopped"),
                "uptime": uptime_str(srv.get("start_time")) if srv.get("status") == "Running" else "0 ثانية",
                "port": srv.get("port", "N/A"),
                "plan": srv.get("plan", "basic"),
                "storage_limit": srv.get("storage_limit", 100),
                "ram_limit": srv.get("ram_limit", 256),
                "cpu_limit": srv.get("cpu_limit", 0.5),
                "disk_used": disk_used_mb
            })
    user = db["users"].get(session["email"], {})
    return jsonify({
        "success": True,
        "servers": user_servers,
        "stats": {
            "used": len(user_servers),
            "total": user.get("max_servers", 5),
            "expiry": user.get("expiry_days", 365),
            "disk_used": round(total_disk_used_mb, 2),
            "disk_total": user.get("storage_limit", 102400),
        }
    })

@app.route('/api/server/add', methods=['POST'])
def add_server():
    if "email" not in session:
        return jsonify({"success": False, "message": "غير مصرح"}), 401
    
    user = db["users"].get(session["email"])
    if not user:
        return jsonify({"success": False, "message": "مستخدم غير موجود"})
    
    user_srv_count = len([s for s in db["servers"].values() if s["owner"] == session["email"]])
    if user_srv_count >= user.get("max_servers", 5):
        return jsonify({"success": False, "message": f"وصلت للحد الأقصى ({user.get('max_servers', 5)}) سيرفر."})
    
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "الرجاء إدخال اسم للسيرفر"})
    
    plan_id = user.get("plan", "basic")
    plan = db["plans"].get(plan_id, db["plans"]["basic"])
    
    safe_email = session['email'].replace('@', '_at_').replace('.', '_dot_')
    folder = f"{safe_email}_{re.sub(r'[^a-zA-Z0-9]', '', name)}_{int(time.time())}"
    path = os.path.join(get_user_servers_dir(session["email"]), folder)
    os.makedirs(path, exist_ok=True)
    assigned_port = get_assigned_port()
    
    db["servers"][folder] = {
        "name": name,
        "owner": session["email"],
        "path": path,
        "type": "Python",
        "status": "Stopped",
        "created_at": str(datetime.now()),
        "startup_file": "",
        "pid": None,
        "port": assigned_port,
        "plan": plan_id,
        "storage_limit": plan["storage"],
        "ram_limit": plan["ram"],
        "cpu_limit": plan["cpu"]
    }
    save_db(db)
    return jsonify({"success": True, "message": f"✅ تم إنشاء الخادم {name}"})

@app.route('/api/server/action/<folder>/<action>', methods=['POST'])
def server_action(folder, action):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False, "message": "غير مصرح"})
    
    if action == "start":
        if srv.get("status") == "Running":
            return jsonify({"success": False, "message": "الخادم يعمل بالفعل"})
        ok, msg = start_server_process(folder)
        return jsonify({"success": ok, "message": msg})
    elif action == "stop":
        stop_server_process(folder)
        return jsonify({"success": True, "message": "🛑 تم الإيقاف"})
    elif action == "restart":
        restart_server(folder)
        return jsonify({"success": True, "message": "🔄 تم إعادة التشغيل"})
    elif action == "delete":
        stop_server_process(folder)
        if os.path.exists(srv["path"]):
            shutil.rmtree(srv["path"], ignore_errors=True)
        del db["servers"][folder]
        save_db(db)
        return jsonify({"success": True, "message": "🗑 تم الحذف"})
    return jsonify({"success": False})

@app.route('/api/server/stats/<folder>')
def get_server_stats(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    status = srv.get("status", "Stopped")
    logs = "لا توجد مخرجات بعد"
    log_path = os.path.join(srv["path"], "out.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.read().split('\n')
                logs = '\n'.join(lines[-500:])
        except Exception:
            pass
    
    errors = ""
    error_path = os.path.join(srv["path"], "errors.log")
    if os.path.exists(error_path):
        try:
            with open(error_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
                if content:
                    errors = '\n'.join(content.split('\n')[-50:])
        except Exception:
            pass
    
    mem_info = "0 MB"
    if srv.get("pid") and status == "Running":
        try:
            p = psutil.Process(srv["pid"])
            mem_info = f"{p.memory_info().rss / (1024*1024):.1f} MB"
        except Exception:
            pass
    
    return jsonify({
        "success": True,
        "status": status,
        "logs": logs,
        "errors": errors,
        "mem": mem_info,
        "uptime": uptime_str(srv.get("start_time")) if status == "Running" else "0 ثانية",
        "port": srv.get("port", "--"),
        "ip": get_public_ip(),
        "type": "Python"
    })

# ============== الملفات ==============
@app.route('/api/files/list/<folder>')
def list_server_files(folder):
    if "email" not in session:
        return jsonify([]), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify([])
    
    path = srv["path"]
    files = []
    try:
        for f in os.listdir(path):
            if f in ['out.log', 'server.log', 'meta.json', 'errors.log']:
                continue
            fpath = os.path.join(path, f)
            stat = os.stat(fpath)
            size_bytes = stat.st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes/1024:.1f} KB"
            else:
                size_str = f"{size_bytes/(1024*1024):.1f} MB"
            files.append({
                "name": f,
                "size": size_str,
                "is_dir": os.path.isdir(fpath),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                "is_zip": f.lower().endswith('.zip')
            })
    except Exception:
        pass
    return jsonify(sorted(files, key=lambda x: (not x['is_dir'], x['name'].lower())))

@app.route('/api/files/content/<folder>/<path:filename>')
def get_file_content(folder, filename):
    if "email" not in session:
        return jsonify({"content": ""}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"content": ""})
    if '..' in filename:
        return jsonify({"content": ""})
    
    fpath = os.path.join(srv["path"], filename)
    if not os.path.exists(fpath) or os.path.isdir(fpath):
        return jsonify({"content": ""})
    try:
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            return jsonify({"content": f.read()})
    except Exception:
        return jsonify({"content": "[ملف ثنائي]"})

@app.route('/api/files/save/<folder>/<path:filename>', methods=['POST'])
def save_file_content(folder, filename):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    if '..' in filename:
        return jsonify({"success": False, "message": "اسم غير صالح"})
    
    data = request.get_json()
    fpath = os.path.join(srv["path"], filename)
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(data.get("content", ""))
        return jsonify({"success": True, "message": "✅ تم الحفظ"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/files/upload/<folder>', methods=['POST'])
def upload_files(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    if not os.path.exists(srv["path"]):
        os.makedirs(srv["path"], exist_ok=True)
    
    files = request.files.getlist('files[]')
    if not files:
        return jsonify({"success": False, "message": "لا توجد ملفات"})
    
    uploaded = 0
    errors_list = []
    for f in files:
        try:
            if not f or not f.filename or '..' in f.filename:
                continue
            save_path = os.path.join(srv["path"], f.filename)
            f.save(save_path)
            uploaded += 1
        except Exception as e:
            errors_list.append(str(e))
    
    if uploaded > 0:
        log_path = os.path.join(srv["path"], "out.log")
        threading.Thread(
            target=_auto_install_after_upload,
            args=(srv["path"], log_path),
            daemon=True
        ).start()
        msg = f"✅ تم رفع {uploaded} ملف"
        if errors_list:
            msg += f" (⚠️ {len(errors_list)} تحذير)"
        return jsonify({"success": True, "message": msg, "warnings": errors_list})
    return jsonify({"success": False, "message": "فشل الرفع", "errors": errors_list})

def _auto_install_after_upload(srv_path: str, log_path: str):
    try:
        with open(log_path, "a", encoding='utf-8') as lf:
            auto_install_deps(srv_path, lf)
    except Exception:
        pass

@app.route('/api/files/rename/<folder>', methods=['POST'])
def rename_file(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    data = request.get_json() or {}
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()
    if not old_name or not new_name or '..' in old_name or '..' in new_name:
        return jsonify({"success": False, "message": "اسم غير صالح"})
    
    old_path = os.path.join(srv["path"], old_name)
    new_path = os.path.join(srv["path"], new_name)
    if not os.path.exists(old_path):
        return jsonify({"success": False, "message": "الملف غير موجود"})
    if os.path.exists(new_path):
        return jsonify({"success": False, "message": "يوجد ملف بهذا الاسم"})
    try:
        os.rename(old_path, new_path)
        if srv.get("startup_file") == old_name:
            srv["startup_file"] = new_name
            save_db(db)
        return jsonify({"success": True, "message": f"✅ تمت إعادة التسمية إلى {new_name}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/files/unzip/<folder>/<path:filename>', methods=['POST'])
def unzip_file(folder, filename):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    if not filename.lower().endswith('.zip'):
        return jsonify({"success": False, "message": "الملف ليس zip"})
    
    zip_path = os.path.join(srv["path"], filename)
    if not os.path.exists(zip_path):
        return jsonify({"success": False, "message": "الملف غير موجود"})
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad = zf.testzip()
            if bad:
                return jsonify({"success": False, "message": f"ملف ZIP تالف: {bad}"})
            zf.extractall(srv["path"])
        return jsonify({"success": True, "message": f"✅ تم فك ضغط {filename}"})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "message": "ملف ZIP غير صالح"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/files/delete/<folder>', methods=['POST'])
def delete_files(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    data = request.get_json() or {}
    names = data.get("names", data.get("name", []))
    if isinstance(names, str):
        names = [names]
    
    deleted = 0
    for name in names:
        if not name or '..' in name:
            continue
        fpath = os.path.join(srv["path"], name)
        try:
            if os.path.isdir(fpath):
                shutil.rmtree(fpath)
            elif os.path.exists(fpath):
                os.remove(fpath)
            deleted += 1
        except Exception:
            pass
    if deleted > 0:
        return jsonify({"success": True, "message": f"🗑 تم حذف {deleted} ملف"})
    return jsonify({"success": False, "message": "فشل الحذف"})

@app.route('/api/files/create/<folder>', methods=['POST'])
def create_file_api(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    data = request.get_json()
    filename = data.get("filename", "").strip()
    if not filename or '..' in filename:
        return jsonify({"success": False, "message": "اسم غير صالح"})
    
    fpath = os.path.join(srv["path"], filename)
    try:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(data.get("content", ""))
        return jsonify({"success": True, "message": f"✅ تم إنشاء {filename}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/server/set-startup/<folder>', methods=['POST'])
def set_startup_file(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    data = request.get_json()
    filename = data.get("filename", "").strip()
    if not filename or '..' in filename:
        return jsonify({"success": False, "message": "اسم غير صالح"})
    if not os.path.exists(os.path.join(srv["path"], filename)):
        return jsonify({"success": False, "message": "الملف غير موجود"})
    
    srv["startup_file"] = filename
    save_db(db)
    return jsonify({"success": True, "message": f"✅ تم تعيين {filename} كملف التشغيل"})

@app.route('/api/server/install/<folder>', methods=['POST'])
def install_requirements(folder):
    if "email" not in session:
        return jsonify({"success": False}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != session["email"]:
        return jsonify({"success": False})
    
    log_path = os.path.join(srv["path"], "out.log")
    deps_file = os.path.join(srv["path"], "requirements.txt")
    if not os.path.exists(deps_file):
        return jsonify({"success": False, "message": "requirements.txt غير موجود"})
    
    try:
        with open(log_path, "a", encoding='utf-8') as lf:
            lf.write(f"\n{'='*50}\n📦 تثبيت المكتبات...\n{'='*50}\n")
        cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        proc = subprocess.Popen(
            cmd,
            cwd=srv["path"],
            stdout=open(log_path, "a", encoding='utf-8'),
            stderr=subprocess.STDOUT
        )
        def wait_install():
            proc.wait()
            with open(log_path, "a", encoding='utf-8') as lf:
                lf.write("\n✅ تم!\n" if proc.returncode == 0 else "\n❌ فشل\n")
        threading.Thread(target=wait_install, daemon=True).start()
        return jsonify({"success": True, "message": "📦 بدأ تثبيت المكتبات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API البوت ==============
@app.route('/api/bot/verify', methods=['POST'])
def bot_verify():
    data = request.get_json()
    api_key = data.get('api_key', '').strip()
    if not api_key:
        return jsonify({"success": False, "message": "API Key مطلوب"})
    email, user = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"})
    return jsonify({
        "success": True,
        "email": email,
        "is_admin": is_admin(email),
        "max_servers": user.get("max_servers", 5),
        "expiry_days": user.get("expiry_days", 365)
    })

@app.route('/api/bot/servers', methods=['GET'])
def bot_list_servers():
    api_key = request.args.get('api_key')
    if not api_key:
        return jsonify({"success": False, "message": "API Key مطلوب"}), 401
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    
    user_servers = []
    for folder, srv in db["servers"].items():
        if srv["owner"] == email:
            user_servers.append({
                "folder": folder,
                "title": srv["name"],
                "status": srv.get("status", "Stopped"),
                "uptime": uptime_str(srv.get("start_time")) if srv.get("status") == "Running" else "0 ثانية",
                "port": srv.get("port", "N/A"),
                "plan": srv.get("plan", "basic"),
                "type": "Python",
                "storage_limit": srv.get("storage_limit", 100),
                "ram_limit": srv.get("ram_limit", 256),
                "cpu_limit": srv.get("cpu_limit", 0.5)
            })
    return jsonify({"success": True, "servers": user_servers})

@app.route('/api/bot/server/action', methods=['POST'])
def bot_server_action():
    data = request.get_json()
    api_key = data.get('api_key')
    folder = data.get('folder')
    action = data.get('action')
    if not all([api_key, folder, action]):
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != email:
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    
    if action == "start":
        if srv.get("status") == "Running":
            return jsonify({"success": False, "message": "السيرفر يعمل بالفعل"})
        ok, msg = start_server_process(folder)
        return jsonify({"success": ok, "message": msg})
    elif action == "stop":
        stop_server_process(folder)
        return jsonify({"success": True, "message": "🛑 تم الإيقاف"})
    elif action == "restart":
        restart_server(folder)
        return jsonify({"success": True, "message": "🔄 تم إعادة التشغيل"})
    elif action == "delete":
        stop_server_process(folder)
        if os.path.exists(srv["path"]):
            shutil.rmtree(srv["path"], ignore_errors=True)
        del db["servers"][folder]
        save_db(db)
        return jsonify({"success": True, "message": "🗑 تم الحذف"})
    return jsonify({"success": False, "message": "إجراء غير معروف"})

@app.route('/api/bot/console', methods=['GET'])
def bot_console():
    api_key = request.args.get('api_key')
    folder = request.args.get('folder')
    if not api_key or not folder:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != email:
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    
    log_path = os.path.join(srv["path"], "out.log")
    logs = "لا توجد مخرجات بعد"
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.read().split('\n')
                logs = '\n'.join(lines[-500:])
        except Exception:
            pass
    return jsonify({"success": True, "logs": logs})

@app.route('/api/bot/errors', methods=['GET'])
def bot_errors():
    api_key = request.args.get('api_key')
    folder = request.args.get('folder')
    if not api_key or not folder:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != email:
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    
    errors = "✅ لا توجد أخطاء مسجلة"
    error_path = os.path.join(srv["path"], "errors.log")
    if os.path.exists(error_path):
        try:
            with open(error_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().strip()
                if content:
                    errors = '\n'.join(content.split('\n')[-300:])
        except Exception:
            pass
    return jsonify({"success": True, "errors": errors})

@app.route('/api/bot/install', methods=['POST'])
def bot_install():
    data = request.get_json()
    api_key = data.get('api_key')
    folder = data.get('folder')
    if not api_key or not folder:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != email:
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    
    log_path = os.path.join(srv["path"], "out.log")
    if not os.path.exists(os.path.join(srv["path"], "requirements.txt")):
        return jsonify({"success": False, "message": "requirements.txt غير موجود"}), 404
    try:
        with open(log_path, "a", encoding='utf-8') as lf:
            lf.write(f"\n{'='*50}\n📦 بدأ تثبيت المكتبات...\n{'='*50}\n")
        cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        proc = subprocess.Popen(cmd, cwd=srv["path"], stdout=open(log_path, "a", encoding='utf-8'), stderr=subprocess.STDOUT)
        def wait_install():
            proc.wait()
            with open(log_path, "a", encoding='utf-8') as lf:
                lf.write("\n✅ تم التثبيت!\n" if proc.returncode == 0 else "\n❌ فشل التثبيت\n")
        threading.Thread(target=wait_install, daemon=True).start()
        return jsonify({"success": True, "message": "📦 بدأ تثبيت المكتبات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/bot/create_server', methods=['POST'])
def bot_create_server():
    data = request.get_json()
    api_key = data.get('api_key')
    name = data.get('name', '').strip()
    if not api_key:
        return jsonify({"success": False, "message": "API Key مطلوب"}), 400
    if not name:
        return jsonify({"success": False, "message": "الرجاء إدخال اسم للسيرفر"}), 400
    
    email, user = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    
    user_srv_count = len([s for s in db["servers"].values() if s["owner"] == email])
    max_allowed = user.get("max_servers", 5)
    if user_srv_count >= max_allowed:
        return jsonify({"success": False, "message": f"وصلت للحد الأقصى ({max_allowed}) سيرفر"})
    
    plan_id = user.get("plan", "basic")
    plan = db["plans"].get(plan_id, db["plans"]["basic"])
    
    safe_email = email.replace('@', '_at_').replace('.', '_dot_')
    folder = f"{safe_email}_{re.sub(r'[^a-zA-Z0-9]', '', name)}_{int(time.time())}"
    path = os.path.join(get_user_servers_dir(email), folder)
    os.makedirs(path, exist_ok=True)
    assigned_port = get_assigned_port()
    
    db["servers"][folder] = {
        "name": name,
        "owner": email,
        "path": path,
        "type": "Python",
        "status": "Stopped",
        "created_at": str(datetime.now()),
        "startup_file": "",
        "pid": None,
        "port": assigned_port,
        "plan": plan_id,
        "storage_limit": plan["storage"],
        "ram_limit": plan["ram"],
        "cpu_limit": plan["cpu"]
    }
    save_db(db)
    return jsonify({"success": True, "message": f"✅ تم إنشاء السيرفر {name}", "folder": folder, "port": assigned_port})

@app.route('/api/bot/set_startup', methods=['POST'])
def bot_set_startup():
    data = request.get_json()
    api_key = data.get('api_key')
    folder = data.get('folder')
    filename = data.get('filename')
    if not all([api_key, folder, filename]):
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400
    email, _ = get_user_by_api_key(api_key)
    if not email:
        return jsonify({"success": False, "message": "API Key غير صالح"}), 401
    srv = db["servers"].get(folder)
    if not srv or srv["owner"] != email:
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    file_path = os.path.join(srv["path"], filename)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "message": "الملف غير موجود"}), 404
    srv["startup_file"] = filename
    save_db(db)
    return jsonify({"success": True, "message": f"✅ تم تعيين {filename} كملف التشغيل"})

# ============== التشغيل ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)