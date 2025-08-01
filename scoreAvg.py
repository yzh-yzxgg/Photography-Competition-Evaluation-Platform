import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()


cursor.execute("SELECT cname, total_score, vote_count FROM photo_scores_certified_users")
rows_certified = cursor.fetchall()

averages_certified = []
for row in rows_certified:
    cname, total_score, vote_count = row
    if vote_count == 0:
        average = 0
    else:
        average = total_score / vote_count
    averages_certified.append((cname, average))

averages_certified.sort(key=lambda x: x[1], reverse=True)

print("===== Certified Users =====")
print("CNAME\tAverage Score")
for cname, avg in averages_certified:
    print(f"{cname}\t{avg:.3f}")

print("\n")


cursor.execute("SELECT cname, total_score, vote_count FROM photo_scores_public_users")
rows_public = cursor.fetchall()

averages_public = []
for row in rows_public:
    cname, total_score, vote_count = row
    if vote_count == 0:
        average = 0
    else:
        average = total_score / vote_count
    averages_public.append((cname, average))

averages_public.sort(key=lambda x: x[1], reverse=True)

print("===== Public Users =====")
print("CNAME\tAverage Score")
for cname, avg in averages_public:
    print(f"{cname}\t{avg:.3f}")

conn.close()
