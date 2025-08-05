"""
app.py  ── Flask + Socket.IO + JWT 로그인 + 채팅 + Kafka + 온라인 사용자 목록
"""
import os, json, threading, jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, make_response
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_bcrypt import Bcrypt

import model  # user CRUD / Kafka consumer·producer / helper 함수

# ■ 기본 설정
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
bcrypt = Bcrypt(app)

# ■ 온라인 사용자 정보
online = {}  # { sid: username }

@socketio.on("connect")
def handle_connect():
    username = request.args.get("user", f"Anon_{request.sid[:5]}")
    online[request.sid] = username
    emit("user_list", list(online.values()), broadcast=True)
    print(f"✅ {username} 온라인 ({len(online)}명)")

@socketio.on("disconnect")
def handle_disconnect():
    username = online.pop(request.sid, None)
    emit("user_list", list(online.values()), broadcast=True)
    print(f"❌ {username} 오프라인 ({len(online)}명)")

# ■ JWT 인증 데코레이터

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return redirect(url_for("login_page"))
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.username = data["username"]
        except jwt.ExpiredSignatureError:
            return "토큰 만료", 401
        except jwt.InvalidTokenError:
            return "토큰 오류", 401
        return f(*args, **kwargs)
    return decorated

# ■ Flask 라우티드
@app.route("/")
def index():
    token = request.cookies.get("access_token")
    username = None
    if token:
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            username = decoded.get("username")
        except jwt.ExpiredSignatureError:
            pass
        except jwt.InvalidTokenError:
            pass
    return render_template("index.html", username=username)

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

@app.route("/login", methods=["POST"])
def login_page():
    username = request.form["username"]
    password = request.form["password"]
    user = model.get_user(username)

    if not user or not bcrypt.check_password_hash(user["password"], password):
        return redirect(url_for("index", error="invalid"))  # 실패 시 index로

    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=2)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    response = make_response(redirect(url_for("index")))  # ✅ index로 리다이렉트
    response.set_cookie("access_token", token, httponly=True, samesite="Lax")
    return response

@app.route("/logout")
def logout():
    response = make_response(redirect(url_for("index")))
    response.delete_cookie("access_token")
    return response

@app.route("/chat")
def chat_page():
    token = request.cookies.get("access_token")
    if not token:
        return redirect(url_for("index"))

    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = data.get("username")
        if not username:
            return redirect(url_for("index"))
    except jwt.ExpiredSignatureError:
        return "토큰 만료", 401
    except jwt.InvalidTokenError:
        return "토큰 오류", 401

    return render_template("chat.html", username=username)


# ■ Socket.IO 이벤트
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
    if not room or not msg:
        return
    user = online.get(request.sid, "Anon")
    payload = model.build_payload(room, user, msg)
    emit("new_message", payload, room=room)
    model.save_message(payload)
    model.publish_kafka(payload)

@socketio.on("leave")
def on_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)
        print(f"👋 {request.sid} left {room}")

# Kafka consumer 드래머 시작

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

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)
