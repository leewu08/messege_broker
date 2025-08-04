"""
app.py ── Flask + Socket.IO 라우팅
"""
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import threading, json

import model  # ← 위에서 만든 모듈

# ─────────────────────── Flask ───────────────────────
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ─────────────────────── HTTP ────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ─────────────────── Socket 이벤트 ───────────────────
@socketio.on("join")
def on_join(data):
    room = data.get("room")
    if not room:
        return
    join_room(room)
    print(f"🚪 {request.sid} joined {room}")

    # 최근 히스토리 전송
    for msg in model.fetch_recent(room):
        emit("new_message", msg, room=request.sid)

@socketio.on("chat_message")
def on_chat(data):
    room, msg = data.get("room"), data.get("msg")
    if not room or not msg:
        return

    payload = model.build_payload(room, data.get("user"), msg)

    # 1) 같은 인스턴스 사용자에게 브로드캐스트
    emit("new_message", payload, room=room)

    # 2) DB 저장 & Kafka 퍼블리시
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

        if payload.get("origin") == model.SERVER_ID:  # 내 메시지 skip
            continue

        model.save_message(payload)
        socketio.emit("new_message", payload, room=payload.get("room"))

threading.Thread(target=kafka_worker, daemon=True).start()

# ─────────────────────── 실행 ────────────────────────
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)