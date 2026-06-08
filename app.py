from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
import sys
import os

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = 'your_secret_key_here'  # 请确保使用安全的密钥

# 确保static文件夹存在
if not os.path.exists('static'):
    os.makedirs('static')

# MongoDB连接配置函数
def get_db():
    try:
        # 设置MongoDB连接超时时间为3秒
        client = MongoClient('mongodb://localhost:27017/', 
                           serverSelectionTimeoutMS=3000,
                           connectTimeoutMS=3000,
                           socketTimeoutMS=3000)
        # 测试连接
        client.server_info()
        db = client['login_system']
        return db
    except Exception as e:
        print(f"MongoDB连接失败: {e}")
        return None

def check_db_connection():
    """检查数据库连接状态"""
    db = get_db()
    if db is None:
        return False
    return True

@app.route('/check_server', methods=['GET'])
def check_server():
    """检查服务器状态的API"""
    if check_db_connection():
        return jsonify({'status': 'success', 'message': '服务器正常'})
    return jsonify({'status': 'error', 'message': '数据库连接失败'})

@app.route('/')
def home():
    """
    如果用户已登录(session中有user_id)，重定向到评论页面
    如果未登录，显示登录页面
    """
    if 'user_id' in session:
        return redirect(url_for('comments'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """
    验证用户名和密码
    登录成功：创建session并更新最后登录时间
    登录失败：返回错误信息
    """
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        username = request.form['username']
        password = request.form['password']
        
        user = db.users.find_one({
            'username': username,
            'password': password
        })
        
        if user:
            session['user_id'] = str(user['_id'])
            session['username'] = username
            # 更新最后登录时间
            db.users.update_one(
                {'_id': user['_id']},
                {'$set': {'last_login': datetime.now()}}
            )
            return jsonify({
                'status': 'success',
                'message': '登录成功！',
                'redirect': '/comments'
            })
        return jsonify({
            'status': 'error',
            'message': '用户名或密码错误！'
        })
    except Exception as e:
        print(f"登录错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请稍后重试'
        })

@app.route('/register', methods=['POST'])
def register():
    """
    检查用户名是否已存在
    创建新用户记录，包含默认头像和统计信息
    注册成功返回成功消息
    """
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        username = request.form['username']
        password = request.form['password']
        
        if db.users.find_one({'username': username}):
            return jsonify({
                'status': 'error',
                'message': '用户名已存在！'
            })
        
        user_data = {
            'username': username,
            'password': password,
            'avatar': '/static/default_avatar.png',
            'created_at': datetime.now(),
            'last_login': datetime.now(),
            'bio': '',
            'posts_count': 0,
            'comments_count': 0
        }
        
        result = db.users.insert_one(user_data)
        
        if result.inserted_id:
            return jsonify({
                'status': 'success',
                'message': '注册成功！'
            })
        return jsonify({
            'status': 'error',
            'message': '注册失败，请重试！'
        })
    except Exception as e:
        print(f"注册错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请重试'
        })

@app.route('/comments')
def comments():
    """
    检查用户是否登录
    获取当前用户信息
    """
    if 'user_id' not in session:
        return redirect(url_for('home'))
    db = get_db()
    if db is None:
        return jsonify({
            'status': 'error',
            'message': '服务器错误：无法连接到数据库，请稍后重试'
        })

    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('comments.html', user=user)

@app.route('/get_posts')
def get_posts():
    """
    获取帖子列表
    支持按最新、最热、评论最多排序
    支持搜索功能
    获取每个帖子的评论信息
    检查当前用户是否对帖子点赞
    """
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        sort_by = request.args.get('sort', 'latest')
        search = request.args.get('search', '')
        
        query = {}
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'content': {'$regex': search, '$options': 'i'}}
            ]
        
        # 更新排序逻辑
        if sort_by == 'hottest':
            sort_field = [('likes_count', -1)]
        elif sort_by == 'most_comments':
            sort_field = [('comments_count', -1)]
        else:  # latest
            sort_field = [('timestamp', -1)]
            
        all_posts = list(db.posts.find(query).sort(sort_field))
        formatted_posts = []
        current_user_id = ObjectId(session['user_id']) if 'user_id' in session else None
        
        for post in all_posts:
            user = db.users.find_one({'_id': post.get('user_id')})
            if not user:
                continue
                
            comments = list(db.comments.find({'post_id': post['_id']}).sort('timestamp', -1))
            formatted_comments = []
            
            for comment in comments:
                comment_user = db.users.find_one({'_id': comment.get('user_id')})
                if not comment_user:
                    continue
                formatted_comments.append({
                    'content': comment.get('content', ''),
                    'username': comment_user.get('username', '未知用户'),
                    'timestamp': comment.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M')
                })
            
            formatted_posts.append({
                'id': str(post['_id']),
                'user_id': str(post.get('user_id')),
                'title': post.get('title', ''),
                'content': post.get('content', ''),
                'username': user.get('username', '未知用户'),
                'timestamp': post.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M'),
                'comments': formatted_comments,
                'likes_count': post.get('likes_count', 0),
                'comments_count': len(formatted_comments),
                'has_liked': current_user_id in post.get('liked_by', [])
            })
        
        return jsonify({
            'status': 'success',
            'posts': formatted_posts
        })
    except Exception as e:
        print(f"获取帖子错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请稍后重试'
        })

@app.route('/post_new', methods=['POST'])
def post_new():
    """
    验证用户登录状态
    检查标题和内容是否为空
    创建新帖子记录
    更新用户发帖数量
    """
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        if 'user_id' not in session:
            return jsonify({
                'status': 'error',
                'message': '请先登录！'
            })
        
        title = request.json.get('title')
        content = request.json.get('content')
        
        if not title or not content:
            return jsonify({
                'status': 'error',
                'message': '标题和内容不能为空！'
            })
        
        post_data = {
            'user_id': ObjectId(session['user_id']),
            'username': session['username'],  # 添加用户名字段
            'title': title,
            'content': content,
            'timestamp': datetime.now(),
            'likes_count': 0,
            'comments_count': 0,
            'liked_by': []
        }
        
        result = db.posts.insert_one(post_data)
        
        if result.inserted_id:
            # 更新用户发帖数
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$inc': {'posts_count': 1}}
            )
            return jsonify({
                'status': 'success',
                'message': '帖子发布成功！'
            })
        return jsonify({
            'status': 'error',
            'message': '发布失败，请重试！'
        })
    except Exception as e:
        print(f"发布帖子错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请稍后重试'
        })

@app.route('/like_post/<post_id>', methods=['POST'])
def like_post(post_id):
    """
    处理帖子点赞/取消点赞
    - 检查用户登录状态
    - 如果已点赞则取消，未点赞则添加
    - 更新帖子点赞数
    """
    if 'user_id' not in session:
        return jsonify({
            'status': 'error',
            'message': '请先登录'
        }), 401
    
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            }), 503

        user_id = ObjectId(session['user_id'])
        post_id = ObjectId(post_id)
        
        # 获取帖子信息
        post = db.posts.find_one({'_id': post_id})
        if not post:
            return jsonify({
                'status': 'error',
                'message': '帖子不存在'
            }), 404
            
        liked_by = post.get('liked_by', [])
        action = 'unliked'
        update_operation = {
            '$pull': {'liked_by': user_id},
            '$inc': {'likes_count': -1}
        }
        
        if user_id not in liked_by:
            action = 'liked'
            update_operation = {
                '$addToSet': {'liked_by': user_id},
                '$inc': {'likes_count': 1}
            }
            
        # 更新帖子
        result = db.posts.update_one(
            {'_id': post_id},
            update_operation
        )
        
        if result.modified_count == 0:
            return jsonify({
                'status': 'error',
                'message': '更新失败，请重试'
            }), 500
            
        # 获取更新后的点赞数
        updated_post = db.posts.find_one(
            {'_id': post_id},
            {'likes_count': 1, 'liked_by': 1}
        )
        
        if not updated_post:
            return jsonify({
                'status': 'error',
                'message': '获取更新后的数据失败'
            }), 500
            
        return jsonify({
            'status': 'success',
            'action': action,
            'likes_count': updated_post.get('likes_count', 0),
            'has_liked': user_id in updated_post.get('liked_by', [])
        })
        
    except Exception as e:
        print(f"点赞处理错误: {str(e)}", file=sys.stderr)
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请稍后重试'
        }), 500

@app.route('/post_comment', methods=['POST'])
def post_comment():
    """
    - 验证用户登录状态
    - 检查评论内容
    - 创建新评论记录
    - 更新用户评论数和帖子评论数
    """
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        if 'user_id' not in session:
            return jsonify({
                'status': 'error',
                'message': '请先登录！'
            })
        
        content = request.json.get('content')
        post_id = request.json.get('post_id')
        
        if not content or not post_id:
            return jsonify({
                'status': 'error',
                'message': '评论内容不能为空！'
            })
        
        comment_data = {
            'user_id': ObjectId(session['user_id']),
            'post_id': ObjectId(post_id),
            'content': content,
            'timestamp': datetime.now()
        }
        
        result = db.comments.insert_one(comment_data)
        
        if result.inserted_id:
            # 更新用户评论数
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$inc': {'comments_count': 1}}
            )
            # 更新帖子评论数
            db.posts.update_one(
                {'_id': ObjectId(post_id)},
                {'$inc': {'comments_count': 1}}
            )
            return jsonify({
                'status': 'success',
                'message': '评论发表成功！'
            })
        return jsonify({
            'status': 'error',
            'message': '评论发表失败，请重试！'
        })
    except Exception as e:
        print(f"发表评论错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '服务器错误，请稍后重试'
        })

@app.route('/my_posts')
def my_posts():
    """获取当前用户的帖子"""
    if 'user_id' not in session:
        return redirect(url_for('home'))
        
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        user_id = ObjectId(session['user_id'])
        user_posts = list(db.posts.find({'user_id': user_id}).sort('timestamp', -1))
        formatted_posts = []
        
        for post in user_posts:
            comments = list(db.comments.find({'post_id': post['_id']}).sort('timestamp', -1))
            formatted_comments = []
            
            for comment in comments:
                comment_user = db.users.find_one({'_id': comment.get('user_id')})
                if comment_user:
                    formatted_comments.append({
                        'content': comment.get('content', ''),
                        'username': comment_user.get('username', '未知用户'),
                        'timestamp': comment.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M')
                    })
            
            user = db.users.find_one({'_id': post.get('user_id')})
            if user:
                formatted_posts.append({
                    'id': str(post['_id']),
                    'user_id': str(post.get('user_id')),
                    'title': post.get('title', ''),
                    'content': post.get('content', ''),
                    'username': user.get('username', '未知用户'),
                    'timestamp': post.get('timestamp', datetime.now()).strftime('%Y-%m-%d %H:%M'),
                    'comments': formatted_comments,
                    'likes_count': post.get('likes_count', 0),
                    'comments_count': len(formatted_comments),
                    'has_liked': user_id in post.get('liked_by', [])
                })
        
        return jsonify({
            'status': 'success',
            'posts': formatted_posts
        })
        
    except Exception as e:
        print(f"获取我的帖子错误: {e}")
        return jsonify({
            'status': 'error',
            'message': '获取帖子失败，请稍后重试'
        })

@app.route('/delete_post/<post_id>', methods=['DELETE'])
def delete_post(post_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': '请先登录'})
    
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'status': 'error',
                'message': '服务器错误：无法连接到数据库，请稍后重试'
            })

        # 获取帖子信息
        post = db.posts.find_one({'_id': ObjectId(post_id)})
        
        if not post:
            return jsonify({'status': 'error', 'message': '帖子不存在'})
            
        # 检查是否是帖子作者（使用user_id进行检查）
        if str(post.get('user_id')) != session['user_id']:
            return jsonify({'status': 'error', 'message': '只能删除自己的帖子'})
            
        # 删除帖子
        result = db.posts.delete_one({'_id': ObjectId(post_id)})
        if result.deleted_count > 0:
            # 更新用户发帖数
            db.users.update_one(
                {'_id': ObjectId(session['user_id'])},
                {'$inc': {'posts_count': -1}}
            )
            return jsonify({'status': 'success', 'message': '帖子已删除'})
        else:
            return jsonify({'status': 'error', 'message': '删除失败'})
    except Exception as e:
        print(f"Error deleting post: {str(e)}", file=sys.stderr)
        return jsonify({'status': 'error', 'message': f'删除失败: {str(e)}'})

@app.route('/logout')
def logout():
    """
    用户登出
    - 清除session中的用户信息
    - 重定向到登录页面
    """
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    # 设置Flask服务器在所有网络接口上监听
    app.run(host='0.0.0.0', port=5000, debug=True)