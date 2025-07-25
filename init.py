import os
import pandas as pd
import random
import hashlib
import sqlite3  # 用于数据库操作

# 定义文件夹路径
folder_path = './uploads'

# 获取文件夹中的所有文件名
file_list = os.listdir(folder_path)

# 过滤出图片文件（假设是常见的图片格式）
image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff')
image_files = [f for f in file_list if f.lower().endswith(image_extensions)]

# 创建DataFrame来存储图片信息
data = {
    'cid': [],     # 图片编号
    'cname': [],   # 照片名字
    'path': []     # 照片完整路径
}

# 创建DataFrame来存储评分信息（总分和投票次数）
score_data = {
    'cid': [],         # 图片编号
    'cname': [],       # 照片名字
    'total_score': [], # 总分，初始0
    'vote_count': [],   # 投票次数，初始0
    'your_life': 0
}

# 定义用户数量
certified_usersum = 10

# 创建DataFrame来存储用户信息（uid与密码）
certified_user_data = {
    'uid': [],        # 用户ID
    'password': [] ,   # 密码
    'token': [],        # 令牌
    'eval_order': []  # 照片评审顺序
}

public_user_data = {
    'uid': [],        # 用户ID
    'token': [],      # 令牌
    'eval_order': []  # 照片评审顺序
}

# 创建DataFrame来存储记录每张照片的投票与否（cid与token）
vote_data = {
    'cid': [],        # 图片编号
    'token_list': [],  # 令牌列表
    'your_life_token_list': []  # YourLife令牌列表
}

# 为每个图片文件生成信息
for idx, image_file in enumerate(image_files, start=1):
    cname, extension = os.path.splitext(image_file)  # 拆分文件名和扩展名
    data['cid'].append(idx)
    score_data['cid'].append(idx)
    vote_data['cid'].append(idx)
    vote_data['token_list'].append('{}')  # 初始化投票列表
    vote_data['your_life_token_list'].append('{}')  # 初始化YourLife令牌列表

    data['cname'].append(cname)
    score_data['cname'].append(cname)

    data['path'].append(image_file)
    score_data['total_score'].append(0)
    score_data['vote_count'].append(0)

# 为认证用户生成信息
eval_order = random.sample(range(1, len(image_files) + 1), len(image_files))
for i in range(certified_usersum):
    certified_user_data['uid'].append(i + 1)  # 用户ID从1开始
    certified_user_data['password'].append(str(random.randint(1000, 9999)))  # 随机四位数字密码
    certified_user_data['token'].append(hashlib.sha256(str(random.getrandbits(256)).encode()).hexdigest()) # 生成随机令牌
    # 生成随机评审顺序，并以逗号分隔的字符串形式存储
    certified_user_data['eval_order'].append(','.join(map(str, eval_order)))  # 随机评审顺序字符串

# 创建DataFrame
df_uploads = pd.DataFrame(data)
df_scores = pd.DataFrame(score_data)
df_certified_users = pd.DataFrame(certified_user_data)
df_public_users = pd.DataFrame(public_user_data)
df_vote_data = pd.DataFrame(vote_data)

# 连接数据库并写入表
conn = sqlite3.connect('database.db')  # 连接到数据库（如果不存在则会创建）

df_uploads.to_sql('uploads', conn, if_exists='replace', index=False)  # 写入uploads表
df_scores.to_sql('photo_scores_certified_users', conn, if_exists='replace', index=False)  # 写入photo_scores_certified_users表
df_scores.to_sql('photo_scores_public_users', conn, if_exists='replace', index=False)  # 写入photo_votes_public_users表
df_certified_users.to_sql('certified_users', conn, if_exists='replace', index=False)  # 写入certified_users表
df_public_users.to_sql('public_users', conn, if_exists='replace', index=False)  # 写入public_users表
df_vote_data.to_sql('user_votes', conn, if_exists='replace', index=False)  # 写入user_votes表

conn.close()  # 关闭数据库连接
