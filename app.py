"""
app.py  ── Flask + Socket.IO + JWT 로그인 + 채팅 + Kafka + 온라인 사용자 목록
"""
import os, json, threading, jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

import model  # user CRUD / Kafka consumer·producer / helper 함수

# ■ 기본 설정
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
bcrypt = Bcrypt(app)

# ■ 온라인 사용자 정보
online = {}  # { sid: username }

@socketio.on("connect")
def handle_connect():
    # ✅ 1. JWT부터 본다 (쿠키에서 access_token 꺼냄)
    token = request.cookies.get("access_token")  
    if not token:
        print("❌ JWT 없음 → 연결 차단")
        disconnect()
        return

    # ✅ 2. JWT 디코딩 시도
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = data.get("username")
        if not username:
            raise jwt.InvalidTokenError("No username in JWT")
    except jwt.ExpiredSignatureError:
        print("❌ JWT 만료 → 연결 차단")
        disconnect()
        return
    except jwt.InvalidTokenError:
        print("❌ JWT 유효하지 않음 → 연결 차단")
        disconnect()
        return

    # ✅ 3. 정상 인증된 유저만 등록
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


########################
#포스트기능 CRUD기능구현예정 db는 몽고db내 post table
########################
# ✅ Create Post
# ✅ 게시글 목록
@app.route('/post')
def post():
    posts = model.get_all_posts()
    if posts is None:
        posts = []
    return render_template('post.html', posts=posts)



# ✅ 게시글 내용 보기
@app.route('/post/<string:post_id>')  # MongoDB는 ObjectId 문자열
def view_post(post_id):
    post = model.get_post(post_id)
    if not post:
        return "게시글이 존재하지 않습니다.", 404
    return render_template('view.html', post=post)

# ✅ 게시글 작성
@app.route('/post/add', methods=['GET', 'POST'])
def add_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        author = request.form.get('author', '익명')

        file = request.files.get('file')
        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        model.create_post(title, content, author, filename)
        return redirect(url_for('post'))
    
    return render_template('add.html')

# ✅ 게시글 수정
@app.route('/post/edit/<string:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    post = model.get_post(post_id)
    if not post:
        return "게시글이 존재하지 않습니다.", 404

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        file = request.files.get('file')
        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        model.update_post(post_id, title, content, filename)
        return redirect(url_for('post'))

    return render_template('edit.html', post=post)

# ✅ 게시글 삭제
@app.route('/post/delete/<string:post_id>')
def delete_post(post_id):
    success = model.delete_post(post_id)
    if success:
        return redirect(url_for('post'))
    return "게시글 삭제 실패", 400

###############################################
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


#---------------------jwt손실 방지책
def get_current_username() -> str | None:
    token = request.cookies.get("access_token")
    if token:
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            return decoded.get("username")
        except:
            return None
    return None


@app.context_processor
def inject_user():
    return {"username": get_current_username()}




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

from flask import request, redirect, url_for, render_template
import jwt

@app.route("/chat")
def chat_page():
    room = request.args.get("room", "")
    token = request.cookies.get("access_token")

    # 1. JWT 토큰 검사
    if not token:
        return redirect(url_for("index"))

    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username = data.get("username")
        if not username:
            return redirect(url_for("index"))
    except jwt.ExpiredSignatureError:
        return "❌ 토큰 만료", 401
    except jwt.InvalidTokenError:
        return "❌ 유효하지 않은 토큰", 401

    # 2. DM 룸 유효성 검사 및 접근 권한 체크
    if not room.startswith("dm_") or len(room.split("_")) != 3:
        return "❌ 잘못된 방 이름", 400

    _, id1, id2 = room.split("_")

    # 현재 접속자가 id1 또는 id2와 일치하지 않으면 거부
    if username not in [id1, id2]:
        return "❌ 이 채팅방에 접근할 수 없습니다", 403

    # 3. 방 이름 정규화 (dm_122_123과 dm_123_122 → 동일하게 처리)
    u1, u2 = sorted([id1, id2])
    normalized_room = f"dm_{u1}_{u2}"

    # 4. 채팅방 입장
    return render_template("chat.html", room=normalized_room, username=username)
@socketio.on("join")
def on_join(data):
    room = data.get("room")
    username = get_current_username()  # JWT에서 username 꺼내는 함수

    if not room or not username:
        return  # 🚫 잘못된 요청 차단

    # ✅ DM 룸 구조인지 확인 (예: dm_122_123)
    if not room.startswith("dm_") or len(room.split("_")) != 3:
        print(f"❌ 잘못된 룸 이름 요청: {room}")
        return

    _, id1, id2 = room.split("_")

    # ✅ 현재 유저가 대화 참여자인지 검증
    if username not in [id1, id2]:
        print(f"⛔️ 접근 불가: {username} tried to join {room}")
        return

    # ✅ 룸 이름 정규화 (122_123 → dm_122_123 고정)
    u1, u2 = sorted([id1, id2])
    normalized_room = f"dm_{u1}_{u2}"

    # ✅ 소켓 입장 처리
    join_room(normalized_room)
    print(f"🚪 {request.sid} ({username}) joined {normalized_room}")

    # ✅ 최근 메시지 가져와서 1:1 전송
    recent_messages = model.fetch_recent(normalized_room)
    for msg in recent_messages:
        emit("new_message", msg, room=request.sid)

@socketio.on("chat_message")
def on_chat(data):
    room = data.get("room")
    msg = data.get("msg")

    if not room or not msg:
        return

    sender = online.get(request.sid, "Anon")

    # ✅ DM 룸 유효성 검사
    if not room.startswith("dm_") or len(room.split("_")) != 3:
        print(f"❌ 잘못된 DM 룸: {room}")
        return

    _, id1, id2 = room.split("_")
    u1, u2 = sorted([id1, id2])
    normalized_room = f"dm_{u1}_{u2}"

    # ✅ sender가 대화 참여자인지 확인
    if sender not in [id1, id2]:
        print(f"⛔️ 접근 불가: {sender} tried to chat in {room}")
        return

    # ✅ receiver 자동 결정
    receiver = u2 if sender == u1 else u1

    # ✅ payload 구성
    payload = model.build_payload(normalized_room, sender, msg)
    payload["receiver"] = receiver  # 리시버 추가

    # ✅ 메시지 전달
    emit("new_message", payload, room=normalized_room)

    # ✅ 저장 및 Kafka 발행
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