import sqlite3
import hashlib
import json
import os
import random
import secrets
import uuid
from datetime import datetime
from flask import Flask, request,render_template,send_file, jsonify

app = Flask(__name__)
database = "database.db"

begin_day=(2025,7,26)

# 初始化会话和用户信息
certified_user_token = []
public_user_token = []


#从SQL取回用户信息
def load_certified_users():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT uid, password, token FROM certified_users")
    users = cursor.fetchall()
    conn.close()
    return users

def load_public_users():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT uid, token FROM public_users")
    users = cursor.fetchall()
    conn.close()
    return users

#对应用户
def update_session():
    global certified_user_token, public_user_token
    certified_users = load_certified_users()
    public_users = load_public_users()

    certified_user_token = {user[0]: user[2] for user in certified_users}
    public_user_token = {user[0]: user[1] for user in public_users}


def get_day():
    begin_date = datetime(*begin_day)
    return (datetime.now() - begin_date).days+1

#用户鉴权
@app.route("/api/v1/session/verify", methods=["GET"])
def session_verify():
    update_session()
    try:
        token = request.headers["X-Session-ID"]
    except KeyError:
        return {"code": 400, "success": False, "data": {"message": "Invalid request"}}
    print (f"Received token: {token}")
    print (f"Certified user tokens: {public_user_token}")
    if token in certified_user_token.values():
        return {
            "code": 200,
            "success": True,
            "data": True,
        }
    elif token in public_user_token.values():
        return {
            "code": 200,
            "success": True,
            "data": False,
        }
    else:
        return {
            "code": 401,
            "success": False,
            "data": {"message": "Invalid session ID"},
        }
    
#大众登录
@app.route("/api/v1/session/public/login", methods=["GET"])
def public_login():
    # 生成一个新的 token
    token = secrets.token_hex(16)

    conn = sqlite3.connect(database)
    cursor = conn.cursor()


    # 插入新用户
    uid = str(uuid.uuid4())
    cursor.execute("INSERT INTO public_users (uid, token) VALUES (?, ?)", (uid, token))

    conn.commit()
    conn.close()

    update_session()
    
    return jsonify({"code": 200, "success": True, "data": {"token": token}})

#获取时间
@app.route("/api/v1/day", methods=["GET"])
def day():
    return {"code": 200, "success": True, "data": get_day()}
    
#投票接口
@app.route("/api/v1/vote/query", methods=["POST"])
def vote_vote():
    update_session()
    token = request.headers.get("X-Session-ID")
    if not token:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})
    if token not in certified_user_token.values() and token not in public_user_token.values():
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})

    data = request.json
    cid = data.get("cid")
    score = data.get("score")  #评审分数1-5

    if cid is None or score is None:
        return jsonify({"code": 400, "success": False, "data": {"message": "cid and score required"}})

    if not (1 <= score <= 5):
        return jsonify({"code": 400, "success": False, "data": {"message": "score must be 1-5"}})

    conn = sqlite3.connect(database)
    cursor = conn.cursor()

    # 获取当前cid投票token_list
    row = conn.execute("SELECT token_list FROM user_votes WHERE cid = ?", (cid,)).fetchone()
    token_list = json.loads(row['token_list']) if row['token_list'] else {}
    pre_score = token_list[token] if token in token_list else 0

    # 更新投票记录
    conn.execute("")

    conn.commit()
    conn.close()

    return jsonify({"code": 200, "success": True, "data": {"message": "Vote recorded successfully"}})


# 查询照片评分统计接口
@app.route("/api/v1/photo/score/<int:cid>", methods=["GET"])
def photo_score(cid):
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT total_score, vote_count FROM photo_scores WHERE cid=?", (cid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"code": 404, "success": False, "data": {"message": "Photo not found"}})

    total_score, vote_count = row
    avg_score = total_score / vote_count if vote_count > 0 else 0

    return jsonify({
        "code": 200,
        "success": True,
        "data": {
            "total_score": total_score,
            "vote_count": vote_count,
            "average_score": round(avg_score, 2)
        }
    })

# 取消投票接口
@app.route("/api/v1/vote/cancel", methods=["POST"])
def vote_cancel():
    update_session()
    uid = get_uid_from_session()
    if not uid:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})

    data = request.json
    cid = data.get("cid")

    if cid is None:
        return jsonify({"code": 400, "success": False, "data": {"message": "cid required"}})

    conn = sqlite3.connect(database)
    cursor = conn.cursor()

    # 查询用户投过的分数
    cursor.execute("SELECT score FROM user_votes WHERE uid=? AND cid=?", (uid, cid))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"code": 404, "success": False, "data": {"message": "No vote to cancel"}})

    user_score = row[0]

    # 删除用户投票记录
    cursor.execute("DELETE FROM user_votes WHERE uid=? AND cid=?", (uid, cid))

    # 更新照片分数和投票次数
    cursor.execute("UPDATE photo_scores SET total_score = total_score - ?, vote_count = vote_count - 1 WHERE cid=?", (user_score, cid))

    conn.commit()
    conn.close()

    return jsonify({"code": 200, "success": True, "data": {"message": "Vote cancelled successfully"}})


@app.route("/favicon.ico")
def favicon():
    return send_file("static/favicon/favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file("uploads/"+filename, mimetype="image/vnd.microsoft.icon")


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/evaluation/<cid>")
def evaluation(cid):
    return render_template("evaluation.html", cid=cid)


if __name__ == "__main__":
    app.run(host='0.0.0.0')