from pymongo import MongoClient
import random

# 连接MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['login_system']
users = db['users']

def generate_password():
    """生成6位随机数密码"""
    return str(random.randint(100000, 999999))

# 更新所有用户的密码
all_users = users.find()
for user in all_users:
    new_password = generate_password()
    users.update_one(
        {'_id': user['_id']},
        {'$set': {'password': new_password}}
    )
    print(f"用户 {user['username']} 的新密码: {new_password}")

print("\n所有用户密码已更新完成！")
client.close()