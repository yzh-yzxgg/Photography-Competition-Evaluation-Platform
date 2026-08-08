import sqlite3
from collections import defaultdict

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# 存储两个表中的平均成绩
public_scores = {}
certified_scores = {}

# 处理 public 表
cursor.execute("SELECT cname, total_score, vote_count FROM photo_scores_public_users")
rows_public = cursor.fetchall()

for cname, total_score, vote_count in rows_public:
    if vote_count == 0:
        avg = 0
    else:
        avg = total_score / vote_count
    public_scores[cname] = avg

# 处理 certified 表
cursor.execute("SELECT cname, total_score, vote_count FROM photo_scores_certified_users")
rows_certified = cursor.fetchall()

for cname, total_score, vote_count in rows_certified:
    if vote_count == 0:
        avg = 0
    else:
        avg = total_score / vote_count
    certified_scores[cname] = avg

# 混合加权平均：公众评审 2/3 + 认证评委 1/3
all_cnames = set(public_scores.keys()) | set(certified_scores.keys())
mixed_scores = []

for cname in all_cnames:
    public_avg = public_scores.get(cname, 0)
    certified_avg = certified_scores.get(cname, 0)
    final_avg = (2/3) * public_avg + (1/3) * certified_avg
    mixed_scores.append((cname, final_avg))

# 排序并输出
mixed_scores.sort(key=lambda x: x[1], reverse=True)

print("===== Mixed Weighted Average (2/3 Public + 1/3 Certified) =====")
print("CNAME\tAverage Score")
for cname, avg in mixed_scores:
    print(f"{cname}\t{avg:.3f}")

conn.close()
