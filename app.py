from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
from kafka import KafkaProducer, KafkaConsumer
from pymongo import MongoClient
from datetime import datetime
import threading, json, uuid, os

"""
Kafka‑Flask Chat Backend (멀티룸)
———————————————
• ObjectId 직렬화 오류, 중복 메시지 등 기존 문제를 해결한 버전
• SERVER_ID 로컬 인스턴스 구분 → 중복 브로드캐스트 방지
• 최근 10개 히스토리 전송 시 _id 제거해 JSON 직렬화 문제 해결
"""

# --------------------------------------------------
# 설정값 & 상수
# --------------------------------------------------
SERVER_ID = os.getenv("SERVER_ID", str(uuid.uuid4())[:8])  # 고유 ID
CHAT_TOPIC = "chat"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# --------------------------------------------------
# Flask & Socket.IO 초기화
# --------------------------------------------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# --------------------------------------------------
# Kafka 설정
# --------------------------------------------------
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP,
    value_serializer=lambda v: v.encode("utf-8"),
)

consumer = KafkaConsumer(
    CHAT_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    group_id=f"chat-backend-{SERVER_ID}",
    auto_offset_reset="latest",
    value_deserializer=lambda m: m.decode("utf-8"),
)

# --------------------------------------------------
# MongoDB 설정
# --------------------------------------------------
client = MongoClient(MONGO_URI)
db = client.chat_db
collection = db.messages

# --------------------------------------------------
# 유틸
# --------------------------------------------------

def _sanitize(doc: dict) -> dict:
    """Mongo 도큐먼트 → JSON 직렬화 가능한 dict"""
    clean = dict(doc)
    clean.pop("_id", None)
    # datetime → iso 문자열 (히스토리 조회 시만 해당)
    if isinstance(clean.get("timestamp"), datetime):
        clean["timestamp"] = clean["timestamp"].isoformat()
    return clean

# --------------------------------------------------
# HTTP 뷰
# --------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# --------------------------------------------------
# Socket.IO 이벤트
# --------------------------------------------------
@socketio.on("join")
def handle_join(data):
    """{room: 'roomA'} 형태로 채팅방 참가"""
    room = data.get("room")
    if not room:
        return

    join_room(room)
    print(f"🚪 {request.sid} joined {room}")

    # 최근 10개 메시지를 클라이언트에 전송 (JSON 직렬화 safe)
    recent = (
        collection.find({"room": room}).sort("timestamp", -1).limit(10)
    )
    for doc in reversed(list(recent)):
        socketio.emit("new_message", _sanitize(doc), room=request.sid)


@socketio.on("chat_message")
def handle_chat_message(data):
    """클라이언트 → 서버 메시지"""
    room = data.get("room")
    msg = data.get("msg")
    if not room or not msg:
        return

    payload = {
        "room": room,
        "user": data.get("user", "익명"),
        "msg": msg,
        "timestamp": datetime.utcnow().isoformat(),
        "origin": SERVER_ID,
    }

    # 같은 프로세스 사용자에게 즉시 브로드캐스트 + 저장
    emit("new_message", payload, room=room)
    collection.insert_one(payload)

    # Kafka 퍼블리시 -> 다른 인스턴스로 전파
    producer.send(CHAT_TOPIC, json.dumps(payload))


@socketio.on("leave")
def handle_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)


@socketio.on("connect")
def on_connect():
    print(f"✅ 클라이언트 접속: {request.sid}")

# --------------------------------------------------
# Kafka → Socket 브로드캐스트 스레드
# --------------------------------------------------

def consume_messages():
    for record in consumer:
        try:
            payload = json.loads(record.value)
        except json.JSONDecodeError:
            continue

        # 내가 보낸 건 패스 (중복 방지)
        if payload.get("origin") == SERVER_ID:
            continue

        room = payload.get("room")
        if not room:
            continue

        collection.insert_one(payload)
        socketio.emit("new_message", payload, room=room)


threading.Thread(target=consume_messages, daemon=True).start()

# --------------------------------------------------
# 실행
# --------------------------------------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)
