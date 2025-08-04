"""
model.py  ── 백엔드 공용 모듈
· Mongo/Kafka 설정
· 메시지 CRUD / 직렬화 헬퍼
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import os, uuid, json
from typing import Dict, Any

from kafka import KafkaProducer, KafkaConsumer
from pymongo import MongoClient



# ─────────────────────── 설정 ────────────────────────
SERVER_ID       = os.getenv("SERVER_ID", uuid.uuid4().hex[:8])
CHAT_TOPIC      = "chat"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
MONGO_URI       = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
KST = timezone(timedelta(hours=9))   # 고정 오프셋 → 서머타임 없는 한국에 안전

def now_kst_iso() -> str:
    """KST(UTC+9) ISO-8601 문자열"""
    return datetime.now(tz=KST).isoformat()

# ─────────────────────── Mongo ───────────────────────
mongo       = MongoClient(MONGO_URI)
db          = mongo.chat_db
collection  = db.messages

# ─────────────────────── Kafka ───────────────────────
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

# ──────────────────── 유틸 / DAO ─────────────────────
def now_iso() -> str:
    """UTC ISO-8601 문자열"""
    return datetime.now(timezone.utc).isoformat()

def sanitize(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Mongo → JSON 직렬화 가능 형태로"""
    d = dict(doc)
    d.pop("_id", None)
    if isinstance(d.get("timestamp"), datetime):
        d["timestamp"] = d["timestamp"].isoformat()
    return d

def save_message(payload: Dict[str, Any]) -> None:
    collection.insert_one(payload)

def fetch_recent(room: str, limit: int = 10):
    cur = (
        collection.find({"room": room})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return [sanitize(d) for d in reversed(list(cur))]

def build_payload(room: str, user: str, msg: str) -> Dict[str, Any]:
    return {
        "room": room,
        "user": user or "익명",
        "msg": msg,
        "timestamp": now_kst_iso(),
        "origin": SERVER_ID,
    }

def publish_kafka(payload: Dict[str, Any]) -> None:
    producer.send(CHAT_TOPIC, json.dumps(payload))