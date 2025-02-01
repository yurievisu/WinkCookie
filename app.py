from flask import Flask, render_template, request, jsonify, send_file, session
import os
import httpx
import json
import time
import hashlib
from datetime import datetime
from functools import wraps
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)

# Constants
COOKIE_FILE = 'data/cookies.json'
ADMIN_FILE = 'data/admin.json'
BACKUP_DIR = 'data/backups'
MAINTENANCE_FILE = 'data/maintenance.json'
TEMP_DIR = 'data/temp'

# Ensure data directory exists
def ensure_directories():
    for directory in ['data', BACKUP_DIR, TEMP_DIR]:
        Path(directory).mkdir(exist_ok=True)

# Initialize files
def init_files():
    if not os.path.exists(ADMIN_FILE):
        os.makedirs(os.path.dirname(ADMIN_FILE), exist_ok=True)
        with open(ADMIN_FILE, 'w') as f:
            json.dump({
                'admins': [hashlib.sha256('admin123'.encode()).hexdigest()]
            }, f)

    if not os.path.exists(MAINTENANCE_FILE):
        os.makedirs(os.path.dirname(MAINTENANCE_FILE), exist_ok=True)
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'maintenance': False}, f)

    if not os.path.exists(COOKIE_FILE):
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, 'w') as f:
            json.dump({'cookies': []}, f)

ensure_directories()
init_files()

def generate_cookie(user, passw):
    """Generate cookie using WinkApi"""
    try:
        headers = {
            'Content-Type': 'application/json',
        }
        
        data = {
            'email': user,
            'password': passw
        }

        client = httpx.Client(timeout=30.0)
        response = client.post(
            'https://winkapi.vercel.app/api/login',
            json=data,
            headers=headers
        ).json()
        
        if response.get('status') == 'success':
            cookie = response.get('cookies')
            uid = response.get('user_id')
            return cookie, uid
        return None, None
    except Exception as e:
        print(f"Error generating cookie: {e}")
        return None, None
    finally:
        client.close()

def save_cookies(cookies_data):
    with open(COOKIE_FILE, 'w') as f:
        if isinstance(cookies_data, dict):
            json.dump(cookies_data, f, indent=4)
        else:
            json.dump({'cookies': cookies_data}, f, indent=4)

def load_cookies():
    try:
        with open(COOKIE_FILE, 'r') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {'cookies': data}
    except FileNotFoundError:
        return {'cookies': []}

def check_maintenance():
    try:
        with open(MAINTENANCE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('maintenance', False)
    except:
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'maintenance': False}, f)
        return False

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def before_request():
    if request.path.startswith('/static/') or request.path.startswith('/admin'):
        return
    if check_maintenance() and request.path != '/':
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Site is under maintenance'}), 503
        return render_template('maintenance.html')

@app.route('/')
def index():
    if check_maintenance():
        return render_template('maintenance.html')
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/add', methods=['POST'])
def add_account():
    if check_maintenance():
        return jsonify({'error': 'Site is under maintenance'}), 503

    data = request.json
    user = data.get('user')
    passw = data.get('password')

    if not all([user, passw]):
        return jsonify({'error': 'Invalid input parameters'}), 400

    cookie, uid = generate_cookie(user, passw)
    
    if cookie and uid:
        cookies_data = load_cookies()
        
        for existing in cookies_data['cookies']:
            if existing['user'] == user:
                return jsonify({'error': 'Account already exists'}), 400
        
        cookies_data['cookies'].append({
            'user': user,
            'password': passw,
            'cookie': cookie,
            'uid': uid,
            'added_date': datetime.now().isoformat(),
            'last_refresh': datetime.now().isoformat()
        })
        
        save_cookies(cookies_data)
        
        return jsonify({
            'success': True,
            'message': 'Account added successfully'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to generate cookie'
        }), 400

@app.route('/api/list', methods=['GET'])
def list_accounts():
    if check_maintenance():
        return jsonify({'error': 'Site is under maintenance'}), 503

    cookies_data = load_cookies()
    return jsonify({
        'success': True,
        'accounts': cookies_data['cookies']
    })

@app.route('/api/delete', methods=['POST'])
def delete_account():
    if check_maintenance():
        return jsonify({'error': 'Site is under maintenance'}), 503

    data = request.json
    user = data.get('user')

    if not user:
        return jsonify({'error': 'User email required'}), 400

    cookies_data = load_cookies()
    original_length = len(cookies_data['cookies'])
    cookies_data['cookies'] = [acc for acc in cookies_data['cookies'] if acc['user'] != user]
    
    if len(cookies_data['cookies']) == original_length:
        return jsonify({'error': 'Account not found'}), 404

    save_cookies(cookies_data)
    return jsonify({
        'success': True,
        'message': 'Account deleted successfully'
    })

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    password = data.get('password')
    if not password:
        return jsonify({'error': 'Password required'}), 400

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    with open(ADMIN_FILE, 'r') as f:
        admin_data = json.load(f)
        if hashed_password in admin_data['admins']:
            session['admin_logged_in'] = True
            return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid password'}), 401

@app.route('/api/admin/maintenance', methods=['POST'])
@admin_required
def toggle_maintenance():
    try:
        current = check_maintenance()
        new_state = not current
        
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'maintenance': new_state}, f)
        
        return jsonify({
            'success': True,
            'maintenance': new_state
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/stats')
@admin_required
def get_stats():
    try:
        cookies_data = load_cookies()
        total_accounts = len(cookies_data.get('cookies', []))
        active_cookies = sum(1 for cookie in cookies_data.get('cookies', []) if cookie.get('cookie'))
        
        return jsonify({
            'total_accounts': total_accounts,
            'active_cookies': active_cookies,
            'maintenance': check_maintenance()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'success': False,
        'error': 'Resource not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
