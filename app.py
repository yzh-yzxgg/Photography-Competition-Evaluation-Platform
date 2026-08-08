import sqlite3
import hashlib
import json
import os
import random
import secrets
import uuid
from datetime import date, datetime
from flask import Flask, request,render_template,send_file, jsonify
from image_variants import ensure_variant, original_path

app = Flask(__name__)
database = "database.db"

EVALUATION_START_DATE = date(2026, 8, 8)
CERTIFIED_DAILY_LIMIT = 50
PUBLIC_DAILY_LIMIT = 30

# 初始化会话和用户信息
certified_user_token = []
public_user_token = []
certified_user_eval_order = []
public_user_eval_order = []
com_data = []

#从SQL取回用户信息
def load_certified_users():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT uid, password, token, eval_order FROM certified_users")
    users = cursor.fetchall()
    conn.close()
    return users

def load_public_users():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT uid, token, eval_order FROM public_users")
    users = cursor.fetchall()
    conn.close()
    return users

def load_com_data():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT cid FROM uploads")
    com_data = cursor.fetchall()
    conn.close()
    return com_data

#对应用户
def update_session():
    global certified_user_token, public_user_token, certified_user_eval_order, public_user_eval_order
    certified_users = load_certified_users()
    public_users = load_public_users()

    certified_user_token = {user[0]: user[2] for user in certified_users}
    public_user_token = {user[0]: user[1] for user in public_users}

    # 更新评审顺序
    certified_user_eval_order = {user[2]: user[3] for user in certified_users}
    public_user_eval_order = {user[1]: user[2] for user in public_users}


def get_day():
    """Return the zero-based number of days since the official start date."""
    return (date.today() - EVALUATION_START_DATE).days


def parse_eval_order(eval_order):
    """Normalize CSV and legacy SQLite numeric evaluation orders."""
    return [int(float(item)) for item in str(eval_order).split(',')]


def get_evaluation_access(token, is_certified):
    eval_order = certified_user_eval_order.get(token) if is_certified else public_user_eval_order.get(token)
    if not eval_order:
        raise ValueError("No evaluation order found")
    eval_order_list = parse_eval_order(eval_order)
    daily_limit = CERTIFIED_DAILY_LIMIT if is_certified else PUBLIC_DAILY_LIMIT
    days_since_start = get_day()
    unlocked_turns = 0 if days_since_start < 0 else min(len(eval_order_list), (days_since_start + 1) * daily_limit)
    return {
        "eval_order": eval_order_list,
        "daily_limit": daily_limit,
        "unlocked_turns": unlocked_turns,
        "days_since_start": days_since_start,
    }


def validate_current_vote(conn, token, is_certified, cid):
    """Allow votes only for the currently opened work within the daily window."""
    try:
        access = get_evaluation_access(token, is_certified)
    except (TypeError, ValueError):
        return False, 500, "Invalid evaluation order"
    if access["unlocked_turns"] == 0:
        return False, 403, "评审将于 2026 年 8 月 8 日开始"

    table = "certified_users" if is_certified else "public_users"
    row = conn.execute(f"SELECT current_turn FROM {table} WHERE token = ?", (token,)).fetchone()
    current_turn = int(float(row[0])) if row and row[0] is not None else 0
    if current_turn < 1 or current_turn > access["unlocked_turns"]:
        return False, 429, f"今日可评作品已达上限（每天 {access['daily_limit']} 张）"
    if access["eval_order"][current_turn - 1] != int(cid):
        return False, 409, "只能为当前正在评审的作品投票"
    return True, 200, ""

#用户鉴权
@app.route("/api/v1/session/verify", methods=["GET"])
def session_verify():
    update_session()
    try:
        token = request.headers["X-Session-ID"]
    except KeyError:
        return {"code": 400, "success": False, "data": {"message": "Invalid request"}}
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
    
# 认证评委登录
@app.route("/api/v1/session/certified/login", methods=["POST"])
def certified_login():
    """Exchange an issued judge password for its existing session token."""
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", "")).strip()
    if not password:
        return jsonify({"code": 400, "success": False, "data": {"message": "Password required"}})

    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM certified_users WHERE password = ?", (password,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid password"}})

    return jsonify({"code": 200, "success": True, "data": {"token": row[0]}})

@app.route("/api/v1/session/public/login", methods=["GET"])
def public_login():
    # 生成一个新的 token
    token = secrets.token_hex(16)

    # 生成随机评审顺序，并以逗号分隔的字符串形式存储
    com_data = load_com_data()
    eval_order = random.sample(range(1, len(com_data) + 1), len(com_data))
    eval_order_str = ','.join(map(str, eval_order))

    conn = sqlite3.connect(database)
    cursor = conn.cursor()


    # 插入新用户
    uid = str(uuid.uuid4())
    cursor.execute("INSERT INTO public_users (uid, token) VALUES (?, ?)", (uid, token))
    cursor.execute("UPDATE public_users SET eval_order = ?, current_turn = ? WHERE uid = ?", (eval_order_str, 1, uid))

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

    is_certified = token in certified_user_token.values()
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    vote_allowed, error_code, error_message = validate_current_vote(conn, token, is_certified, cid)
    if not vote_allowed:
        conn.close()
        return jsonify({"code": error_code, "success": False, "data": {"message": error_message}}), error_code

    # 获取当前cid投票token_list
    row = conn.execute("SELECT token_list FROM user_votes WHERE cid = ?", (cid,)).fetchone()
    token_list = json.loads(row[0]) if row and row[0] else {}  # 检查 row[0] 是否非空
    pre_score = token_list[token] if token in token_list else 0
    token_list[token] = score
    # 更新投票记录
    conn.execute("UPDATE user_votes SET token_list = ? WHERE cid = ?", (json.dumps(token_list), cid))
    # 更新照片分数和投票次数
    if is_certified:
        if pre_score == 0:
            cursor.execute("UPDATE photo_scores_certified_users SET total_score = total_score + ?, vote_count = vote_count + 1 WHERE cid = ?", (score - pre_score, cid))
        else:
            cursor.execute("UPDATE photo_scores_certified_users SET total_score = total_score + ? WHERE cid = ?", (score - pre_score, cid))
    else:
        if pre_score == 0:
            cursor.execute("UPDATE photo_scores_public_users SET total_score = total_score + ?, vote_count = vote_count + 1 WHERE cid = ?", (score - pre_score, cid))
        else:
            cursor.execute("UPDATE photo_scores_public_users SET total_score = total_score + ? WHERE cid = ?", (score - pre_score, cid))
    conn.commit()
    conn.close()

    return jsonify({"code": 200, "success": True, "data": {"message": "Vote recorded successfully"}})

# your life投票接口
@app.route("/api/v1/vote/yourlife", methods=["POST"])
def vote_yourlife():
    update_session()
    token = request.headers.get("X-Session-ID")
    if not token:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})
    if token not in certified_user_token.values() and token not in public_user_token.values():
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})

    data = request.json
    cid = data.get("cid")
    your_life = data.get("interesting")  # 是否投票YourLife

    if cid is None:
        return jsonify({"code": 400, "success": False, "data": {"message": "cid required"}})

    is_certified = token in certified_user_token.values()
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    vote_allowed, error_code, error_message = validate_current_vote(conn, token, is_certified, cid)
    if not vote_allowed:
        conn.close()
        return jsonify({"code": error_code, "success": False, "data": {"message": error_message}}), error_code

    # 获取当前cid投票your_life_token_list
    row = conn.execute("SELECT your_life_token_list FROM user_votes WHERE cid = ?", (cid,)).fetchone()
    your_life_token_list = json.loads(row[0]) if row and row[0] else {}  # 检查 row[0] 是否非空
    pre_your_life = your_life_token_list.get(token, False)
    your_life_token_list[token] = your_life
    # 更新投票记录
    conn.execute("UPDATE user_votes SET your_life_token_list = ? WHERE cid = ?", (json.dumps(your_life_token_list), cid))
    # 更新照片的YourLife投票状态
    if is_certified:
        if your_life:
            if not pre_your_life:
                cursor.execute("UPDATE photo_scores_certified_users SET your_life = your_life + 1 WHERE cid = ?", (cid,))
            else:
                cursor.execute("UPDATE photo_scores_certified_users SET your_life = your_life - 1 WHERE cid = ?", (cid,))
        else:
            if pre_your_life:
                cursor.execute("UPDATE photo_scores_certified_users SET your_life = your_life - 1 WHERE cid = ?", (cid,))
            else:
                cursor.execute("UPDATE photo_scores_certified_users SET your_life = your_life + 1 WHERE cid = ?", (cid,))
    else:
        if your_life:
            if not pre_your_life:
                cursor.execute("UPDATE photo_scores_public_users SET your_life = your_life + 1 WHERE cid = ?", (cid,))
            else:
                cursor.execute("UPDATE photo_scores_public_users SET your_life = your_life - 1 WHERE cid = ?", (cid,))
        else:
            if pre_your_life:
                cursor.execute("UPDATE photo_scores_public_users SET your_life = your_life - 1 WHERE cid = ?", (cid,))
            else:
                cursor.execute("UPDATE photo_scores_public_users SET your_life = your_life + 1 WHERE cid = ?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"code": 200, "success": True, "data": {"message": "YourLife vote recorded successfully"}})


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

# 查询总榜前三 API：展示大众评审热度。
@app.route("/api/v1/rank/main_top3", methods=["GET"])
def get_main_top3():
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT uploads.cid, uploads.path, public.total_score
            FROM photo_scores_public_users AS public
            JOIN uploads ON uploads.cid = public.cid
            WHERE public.total_score IS NOT NULL
            ORDER BY public.total_score DESC, uploads.cid ASC
            LIMIT 3;
        """)
        results = cursor.fetchall()

        top3 = []
        for cid, image_path, score in results:
            top3.append({
                "image_url": f"/media/thumbnail/{image_path}",
                "score": round(score, 2)
            })

        conn.close()

        return jsonify({
            "success": True,
            "data": top3
        })

    except Exception as e:
        print("Error:", e)
        return jsonify({
            "success": False,
            "error": str(e)
        })


# 查询 YourLife 榜单前三：展示大众评审热度。
@app.route("/api/v1/rank/yourlife_top3", methods=["GET"])
def get_yourlife_top3():
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT uploads.cid, uploads.path, public.your_life
            FROM photo_scores_public_users AS public
            JOIN uploads ON uploads.cid = public.cid
            WHERE public.your_life IS NOT NULL
            ORDER BY public.your_life DESC, uploads.cid ASC
            LIMIT 3;
        """)
        results = cursor.fetchall()

        top3 = []
        for cid, image_path, score in results:
            top3.append({
                "image_url": f"/media/thumbnail/{image_path}",
                "score": round(score, 2)
            })

        conn.close()

        return jsonify({
            "success": True,
            "data": top3
        })

    except Exception as e:
        print("Error:", e)
        return jsonify({
            "success": False,
            "error": str(e)
        })

# 查询当前评审turn
@app.route("/api/v1/com/current-turn", methods=["GET"])
def current_turn():
    update_session()
    token = request.headers.get("X-Session-ID")
    if not token:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})
    
    if token not in certified_user_token.values() and token not in public_user_token.values():
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})

    is_certified = token in certified_user_token.values()
    try:
        access = get_evaluation_access(token, is_certified)
    except (TypeError, ValueError):
        return jsonify({"code": 500, "success": False, "data": {"message": "Invalid evaluation order"}})

    # 获取当前评审进度
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    if is_certified:
        cursor.execute("SELECT current_turn FROM certified_users WHERE token=?", (token,))
        result = cursor.fetchone()
        if result:
            current_turn = result[0]
        else:
            return jsonify({"code": 404, "success": False, "data": {"message": "Current turn not found"}})
    else:
        cursor.execute("SELECT current_turn FROM public_users WHERE token=?", (token,))
        result = cursor.fetchone()
        if result:
            current_turn = result[0]
        else:
            return jsonify({"code": 404, "success": False, "data": {"message": "Current turn not found"}})

    conn.close()
    return jsonify({
        "code": 200,
        "success": True,
        "data": {
            "turn": int(float(current_turn)),
            "daily_limit": access["daily_limit"],
            "unlocked_turns": access["unlocked_turns"],
            "starts_on": EVALUATION_START_DATE.isoformat(),
        },
    })

# 给出用户评审turn查询图片信息info
@app.route("/api/v1/com/info", methods=["POST"])
def photo_info():
    data = request.get_json()
    update_session()
    token = request.headers.get("X-Session-ID")
    if not token:
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})
    
    if token not in certified_user_token.values() and token not in public_user_token.values():
        return jsonify({"code": 401, "success": False, "data": {"message": "Invalid session ID"}})

    is_certified = token in certified_user_token.values()
    try:
        access = get_evaluation_access(token, is_certified)
    except (TypeError, ValueError):
        return jsonify({"code": 500, "success": False, "data": {"message": "Invalid evaluation order"}})

    try:
        turn = int(data.get('turn', 1))
    except (ValueError, IndexError):
        return jsonify({"code": 400, "success": False, "data": {"message": "Invalid turn"}})
    if access["unlocked_turns"] == 0:
        return jsonify({"code": 403, "success": False, "data": {"message": "评审将于 2026 年 8 月 7 日开始"}}), 403
    if turn < 1 or turn > access["unlocked_turns"]:
        return jsonify({
            "code": 429,
            "success": False,
            "data": {"message": f"今日可评作品已达上限（每天 {access['daily_limit']} 张）", "unlocked_turns": access["unlocked_turns"]},
        }), 429
    cid = access["eval_order"][turn - 1]

    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    if is_certified:
        cursor.execute("UPDATE certified_users SET current_turn = ? WHERE token = ?", (turn, token))
    else:
        cursor.execute("UPDATE public_users SET current_turn = ? WHERE token = ?", (turn, token))
    
    cursor.execute("SELECT cname, path FROM uploads WHERE cid=?", (cid,))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({"code": 404, "success": False, "data": {"message": "Photo not found"}})

    cname, path = row
    # Return this evaluator's previous choices as well, so revisiting a work
    # restores the visible state instead of looking like it was never scored.
    cursor.execute("SELECT token_list, your_life_token_list FROM user_votes WHERE cid=?", (cid,))
    vote_row = cursor.fetchone()
    score = None
    your_life = False
    if vote_row:
        try:
            score = json.loads(vote_row[0] or "{}").get(token)
            your_life = bool(json.loads(vote_row[1] or "{}").get(token, False))
        except (TypeError, json.JSONDecodeError):
            pass
    conn.commit()
    conn.close()

    return jsonify({
        "code": 200,
        "success": True,
        "data": {
            "cid": cid,
            "cname": cname,
            "path": path,
            "image_url": f"/media/review/{path}",
            "original_image_url": f"/uploads/{path}",
            "score": score,
            "your_life": your_life
        }
    })

@app.route("/favicon.ico")
def favicon():
    return send_file("static/favicon/favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/favicon.svg")
def favicon_svg():
    return send_file("favicon.svg", mimetype="image/svg+xml")

@app.route("/index.avif")
def homepage_image():
    return send_file("index.avif", mimetype="image/avif", conditional=True, max_age=31536000)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        path = original_path(filename)
    except ValueError:
        return jsonify({"code": 400, "success": False, "data": {"message": "Invalid image path"}}), 400
    if not path.is_file():
        return jsonify({"code": 404, "success": False, "data": {"message": "Photo not found"}}), 404
    return send_file(path, conditional=True, max_age=31536000)

@app.route('/media/<variant>/<filename>')
def optimized_image(variant, filename):
    if variant not in ("review", "thumbnail"):
        return jsonify({"code": 404, "success": False, "data": {"message": "Image variant not found"}}), 404
    try:
        path = ensure_variant(filename, variant)
    except (FileNotFoundError, OSError, ValueError):
        return jsonify({"code": 404, "success": False, "data": {"message": "Photo not found"}}), 404
    return send_file(path, mimetype="image/webp", conditional=True, max_age=31536000)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/evaluation/<turn>")
def evaluation(turn):
    return render_template("evaluation.html", turn=turn)


if __name__ == "__main__":
    app.run(host='0.0.0.0')
