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

session = []
session_find = {}

#从SQL取回用户信息
def load_users():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT uid,password FROM user")
    users = cursor.fetchall()
    conn.close()
    return users

#对应用户
def update_session():
    session.clear()
    session_find.clear()
    users = load_users()
    for username, password in users:
        session.append(password)
        session_find[password] = username


def get_uid_from_session():
    try:
        session_id = request.headers["X-Session-ID"]
    except KeyError:
        return None
    return session_find.get(session_id)

def get_day():
    begin_date = datetime(*begin_day)
    return (datetime.now() - begin_date).days+1

#用户鉴权
@app.route("/api/v1/session/verify", methods=["GET"])
def session_verify():
    update_session()
    try:
        session_id = request.headers["X-Session-ID"]
    except KeyError:
        return {"code": 400, "success": False, "data": {"message": "Invalid request"}}
    if session_id in session:
        return {
            "code": 200,
            "success": True,
        }
    else:
        return {
            "code": 401,
            "success": False,
            "data": {"message": "Invalid session ID"},
        }
    
#获取时间
@app.route("/api/v1/day", methods=["GET"])
def day():
    return {"code": 200, "success": True, "data": get_day()}
    
#投票接口
@app.route("/api/v1/vote/query", methods=["POST"])
def vote_vote():
    update_session()
    uid = get_uid_from_session()
    if not uid:
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

    # 检查是否重投
    cursor.execute("SELECT score FROM user_votes WHERE uid=? AND cid=?", (uid, cid))
    existing = cursor.fetchone()

    if existing:
        # 拒绝投票
        conn.close()
        return jsonify({"code": 409, "success": False, "data": {"message": "You have already voted for this photo"}})

    # 插入投票记录
    cursor.execute("INSERT INTO user_votes (uid, cid, score) VALUES (?, ?, ?)", (uid, cid, score))

    # 更新总分和投票数
    cursor.execute("UPDATE photo_scores SET total_score = total_score + ?, vote_count = vote_count + 1 WHERE cid=?", (score, cid))

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