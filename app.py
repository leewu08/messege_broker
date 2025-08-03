from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from kafka import KafkaProducer, KafkaConsumer
from pymongo import MongoClient
from datetime import datetime
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ✅ Kafka 설정
producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=lambda v: v.encode('utf-8'))
consumer = KafkaConsumer('chat', bootstrap_servers='localhost:9092', auto_offset_reset='latest', value_deserializer=lambda m: m.decode('utf-8'))

# ✅ MongoDB 설정
client = MongoClient('mongodb://localhost:27017/')
db = client.chat_db
collection = db.messages

@app.route("/")
def index():
    return render_template("index.html")

# ✅ 사용자 메시지 → Kafka 전송
@socketio.on("chat_message")
def handle_chat_message(msg):
    print("📨 사용자 → Kafka 전송:", msg)
    producer.send('chat', msg)
    collection.insert_one({
        "message": msg,
        "timestamp": datetime.utcnow(),
        "source": "socket"
    })


    

# ✅ Kafka → 사용자 브로드캐스트 + 저장
def consume_messages():
    for message in consumer:
        print("📬 Kafka → 사용자 broadcast:", message.value)
        socketio.emit("new_message", message.value)
        collection.insert_one({
            "message": message.value,
            "timestamp": datetime.utcnow(),
            "source": "kafka"
        })

# ✅ Consumer 스레드 시작
threading.Thread(target=consume_messages, daemon=True).start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)