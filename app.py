"""
app.py ── Flask + Socket.IO + 로그인 라우팅 분리
"""
from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_bcrypt import Bcrypt
import threading, json, datetime, jwt, os

import model  # ← 위에서 만든 모듈

# ─────────────────────── Flask ───────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
bcrypt = Bcrypt(app)

# ─────────────────────── 라우팅 ────────────────────────
from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO
from flask_bcrypt import Bcrypt
import model  # ↖️ 유저 CRUD 함수 들어있다고 가정

app = Flask(__name__)
app.secret_key = "your_secret"
socketio = SocketIO(app)
bcrypt = Bcrypt(app)

# ─────────────────────── 라우팅 ───────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ---------- 회원가입 ----------
@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if model.user_exists(username):
            return "이미 존재하는 아이디입니다."

        # 비밀번호 해시 저장
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        model.create_user(username, hashed_pw)

        # 회원가입 후 로그인 페이지로 이동
        return redirect(url_for("login_page"))
    return render_template("register.html")


# ---------- 로그인 ----------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = model.get_user(username)
        if not user or not bcrypt.check_password_hash(user["password"], password):
            return "로그인 실패"

        # 세션에 로그인 기록
        session["username"] = username
        return redirect(url_for("chat_page"))

    return render_template("login.html")

# ---------- 로그아웃 ----------

@app.route("/logout")
def logout():
    session.clear()  # 모든 세션 데이터 삭제
    return redirect(url_for("index"))  # 메인페이지나 원하는 곳으로 이동

@app.route("/chat")
def chat_page():
    return render_template("chat.html")


# ─────────────────── Socket 이벤트 ───────────────────
@socketio.on("join")
def on_join(data):
    room = data.get("room")
    if not room:
        return
    join_room(room)
    print(f"🚪 {request.sid} joined {room}")

    for msg in model.fetch_recent(room):
        emit("new_message", msg, room=request.sid)

@socketio.on("chat_message")
def on_chat(data):
    room, msg = data.get("room"), data.get("msg")
    token = data.get("token")
    user = model.decode_token(token, app.secret_key) if token else data.get("user")
    if not room or not msg:
        return
    payload = model.build_payload(room, user, msg)
    emit("new_message", payload, room=room)
    model.save_message(payload)
    model.publish_kafka(payload)

@socketio.on("leave")
def on_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)

@socketio.on("connect")
def on_connect():
    print(f"✅ client {request.sid} connected")

# ─────── Kafka → Socket 브로드캐스트 백그라운드 ───────
def kafka_worker():
    for rec in model.consumer:
        try:
            payload = json.loads(rec.value)
        except json.JSONDecodeError:
            continue

        if payload.get("origin") == model.SERVER_ID:
            continue

        model.save_message(payload)
        socketio.emit("new_message", payload, room=payload.get("room"))

threading.Thread(target=kafka_worker, daemon=True).start()

# ─────────────────────── 실행 ────────────────────────
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)
