"""
app.py  ── Flask + Socket.IO + 로그인/채팅 + Kafka + 온라인 사용자 목록
"""
import os, json, threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_bcrypt import Bcrypt

import model           # ← user CRUD / Kafka consumer·producer / helper 함수

# ─────────────────────── 기본 설정 ───────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
bcrypt   = Bcrypt(app)

# ─────────────────────── 온라인 사용자 ─────────────────────
online = {}            # { sid: username }

@socketio.on("connect")
def handle_connect():
    """
    클라이언트가 `io("/?user=닉네임")` 형태로 접속한다고 가정.
    로그인하지 않은 경우엔 익명 ID 부여.
    """
    username = request.args.get("user", f"Anon_{request.sid[:5]}")
    online[request.sid] = username
    emit("user_list", list(online.values()), broadcast=True)
    print(f"✅ {username} 온라인 ({len(online)}명)")

@socketio.on("disconnect")
def handle_disconnect():
    username = online.pop(request.sid, None)
    emit("user_list", list(online.values()), broadcast=True)
    print(f"❌ {username} 오프라인 ({len(online)}명)")

# ─────────────────────── Flask 라우팅 ──────────────────────
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

        hashed = bcrypt.generate_password_hash(password).decode()
        model.create_user(username, hashed)
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

        session["username"] = username
        return redirect(url_for("chat_page"))
    return render_template("login.html")

# ---------- 로그아웃 ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------- 채팅 ----------
@app.route("/chat")
def chat_page():
    # 템플릿에서 JS 소켓 연결할 때  `io('/?user={{ username }}')` 로 쿼리스트링 전달
    return render_template("chat.html", username=session.get("username", ""))

# ─────────────────── Socket 이벤트 ────────────────────
@socketio.on("join")
def on_join(data):
    room = data.get("room")
    if not room:
        return
    join_room(room)
    print(f"🚪 {request.sid} joined {room}")

    # 최근 메시지 히스토리 전송
    for msg in model.fetch_recent(room):
        emit("new_message", msg, room=request.sid)

@socketio.on("chat_message")
def on_chat(data):
    room, msg = data.get("room"), data.get("msg")
    if not room or not msg:
        return

    user = online.get(request.sid, "Anon")
    payload = model.build_payload(room, user, msg)
    emit("new_message", payload, room=room)

    model.save_message(payload)      # Mongo 저장
    model.publish_kafka(payload)     # Kafka 브로커로 발행

@socketio.on("leave")
def on_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)
        print(f"👋 {request.sid} left {room}")

# ─────── Kafka → Socket 브로드캐스트 (백그라운드) ───────
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