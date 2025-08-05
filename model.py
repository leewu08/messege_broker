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
from bson import ObjectId  # 상단에 import 필요
from typing import Optional
f



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
posts_col  = db.post        # ✅ ✅ 게시글 컬렉션 ← 이 줄이 빠진 거야
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

# ─────────────────────── 게시글 CRUD ──────────────────────
def create_post(title: str, content: str, author: str = "익명", filename: Optional[str] = None) -> str:
    """게시글 생성"""
    post = {
        "title": title,
        "content": content,
        "author": author,
        "created_at": _now_kst()
    }
    if filename:
        post["filename"] = filename

    result = posts_col.insert_one(post)
    return str(result.inserted_id)

def get_post(post_id: str) -> Optional[Dict[str, Any]]:
    """게시글 하나 조회"""
    try:
        post = posts_col.find_one({"_id": ObjectId(post_id)})
    except Exception:
        return None

    if post:
        post["_id"] = str(post["_id"])
    return post

def get_all_posts(limit: int = 20) -> List[Dict[str, Any]]:
    """전체 게시글 조회 (최신순)"""
    cursor = posts_col.find().sort("created_at", -1).limit(limit)
    return [
        {**doc, "_id": str(doc["_id"])}
        for doc in cursor
    ]

def update_post(post_id: str, title: str, content: str, filename: Optional[str] = None) -> bool:
    """게시글 수정"""
    update_fields = {
        "title": title,
        "content": content
    }
    if filename:
        update_fields["filename"] = filename

    try:
        result = posts_col.update_one(
            {"_id": ObjectId(post_id)},
            {"$set": update_fields}
        )
        return result.matched_count == 1
    except Exception:
        return False

def delete_post(post_id: str) -> bool:
    """게시글 삭제"""
    try:
        result = posts_col.delete_one({"_id": ObjectId(post_id)})
        return result.deleted_count == 1
    except Exception:
        return False


