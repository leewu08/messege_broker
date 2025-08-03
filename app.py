# app.py
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from kafka import KafkaProducer, KafkaConsumer
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Kafka 설정
producer = KafkaProducer(bootstrap_servers='localhost:9092', value_serializer=lambda v: v.encode('utf-8'))
consumer = KafkaConsumer('chat', bootstrap_servers='localhost:9092', auto_offset_reset='latest', value_deserializer=lambda m: m.decode('utf-8'))

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("chat_message")
def handle_chat_message(msg):
    print("📨 사용자 → Kafka 전송:", msg)
    producer.send('chat', msg)

# Kafka 메시지를 브로드캐스트
def consume_messages():
    for message in consumer:
        print("📬 Kafka → 모든 유저에게:", message.value)
        socketio.emit("new_message", message.value)

# Kafka consumer 스레드 실행
threading.Thread(target=consume_messages, daemon=True).start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80)