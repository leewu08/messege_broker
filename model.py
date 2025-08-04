from __future__ import annotations
"""
model.py – 통합 백엔드 모듈
· MongoDB 설정 (유저 & 메시지)
· Kafka 설정
· 로그인/회원가입 CRUD
· 메시지 CRUD & 직렬화
"""

import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from kafka import KafkaConsumer, KafkaProducer
from pymongo import MongoClient

# ─────────────────────── 환경 설정 ───────────────────────
MONGO_URI: str       = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
KAFKA_BOOTSTRAP: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
CHAT_TOPIC: str      = "chat"
SERVER_ID: str       = os.getenv("SERVER_ID", uuid.uuid4().hex[:8])
KST                  = timezone(timedelta(hours=9))  # 한국 고정 오프셋

# ─────────────────────── MongoDB ───────────────────────
mongo       = MongoClient(MONGO_URI)
db          = mongo.chat_db
users_col   = db.users       # 회원 정보 저장
msgs_col    = db.messages    # 채팅 로그 저장

# ─────────────────────── Kafka ─────────────────────────
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

# ─────────────────────── 유저 CRUD ──────────────────────

def user_exists(username: str) -> bool:
    """username 중복 여부 검사"""
    return users_col.count_documents({"username": username}, limit=1) == 1

def create_user(username: str, hashed_pw: str) -> None:
    """신규 회원 생성 (비밀번호는 이미 해시된 상태로 전달)"""
    users_col.insert_one({
        "username": username,
        "password": hashed_pw,
        "created_at": datetime.utcnow()
    })

def get_user(username: str) -> Dict[str, Any] | None:
    """단일 사용자 조회 (없으면 None)"""
    return users_col.find_one({"username": username})

def generate_anon_name() -> str:
    """익명 닉네임 생성기"""
    return f"익명#{random.randint(1000, 9999)}"

# ─────────────────────── 시간 유틸 ─────────────────────

def _now_kst() -> str:
    """KST ISO8601 문자열"""
    return datetime.now(tz=KST).isoformat()

# ─────────────────────── 메시지 유틸 ────────────────────

def build_payload(room: str, user: str | None, msg: str) -> Dict[str, Any]:
    """클라이언트 → 서버 메시지 공통 포맷 생성"""
    return {
        "room": room,
        "user": user or generate_anon_name(),
        "msg": msg,
        "timestamp": _now_kst(),
        "origin": SERVER_ID,
    }

def save_message(payload: Dict[str, Any]) -> None:
    """MongoDB에 메시지 저장"""
    msgs_col.insert_one(payload)

def publish_kafka(payload: Dict[str, Any]) -> None:
    """Kafka 토픽에 메시지 발행"""
    producer.send(CHAT_TOPIC, json.dumps(payload))

def fetch_recent(room: str, limit: int = 10) -> List[Dict[str, Any]]:
    """최근 메시지 조회 (오래된 순)"""
    cur = msgs_col.find({"room": room}).sort("timestamp", -1).limit(limit)
    docs = list(cur)[::-1]
    for d in docs:
        d.pop("_id", None)
    return docs
