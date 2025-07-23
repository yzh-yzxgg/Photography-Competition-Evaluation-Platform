import os
import pandas as pd
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
    'vote_count': []   # 投票次数，初始0
}

# 为每个图片文件生成信息
for idx, image_file in enumerate(image_files, start=1):
    cname, extension = os.path.splitext(image_file)  # 拆分文件名和扩展名
    data['cid'].append(idx)
    score_data['cid'].append(idx)

    data['cname'].append(cname)
    score_data['cname'].append(cname)

    data['path'].append(image_file)
    score_data['total_score'].append(0)
    score_data['vote_count'].append(0)

# 创建DataFrame
df_uploads = pd.DataFrame(data)
df_scores = pd.DataFrame(score_data)

# 连接数据库并写入表
conn = sqlite3.connect('database.db')  # 连接到数据库（如果不存在则会创建）

df_uploads.to_sql('uploads', conn, if_exists='replace', index=False)  # 写入uploads表
df_scores.to_sql('photo_scores', conn, if_exists='replace', index=False)  # 写入photo_scores表

conn.close()  # 关闭数据库连接
