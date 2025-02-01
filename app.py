from flask import Flask, render_template, request, jsonify, send_file, session
import os
import httpx
import json
import time
import hashlib
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# In-memory storage for serverless environment
COOKIES_DATA = {'cookies': []}
MAINTENANCE_MODE = False
ADMIN_PASSWORD = hashlib.sha256('admin123'.encode()).hexdigest()

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

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if MAINTENANCE_MODE:
        return render_template('maintenance.html')
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/add', methods=['POST'])
def add_account():
    if MAINTENANCE_MODE:
        return jsonify({'error': 'Site is under maintenance'}), 503

    data = request.json
    user = data.get('user')
    passw = data.get('password')

    if not all([user, passw]):
        return jsonify({'error': 'Invalid input parameters'}), 400

    cookie, uid = generate_cookie(user, passw)
    
    if cookie and uid:
        # Check if account already exists
        for existing in COOKIES_DATA['cookies']:
            if existing['user'] == user:
                return jsonify({'error': 'Account already exists'}), 400
        
        # Add new account
        COOKIES_DATA['cookies'].append({
            'user': user,
            'password': passw,
            'cookie': cookie,
            'uid': uid,
            'added_date': datetime.now().isoformat(),
            'last_refresh': datetime.now().isoformat()
        })
        
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
    if MAINTENANCE_MODE:
        return jsonify({'error': 'Site is under maintenance'}), 503

    return jsonify({
        'success': True,
        'accounts': COOKIES_DATA['cookies']
    })

@app.route('/api/delete', methods=['POST'])
def delete_account():
    if MAINTENANCE_MODE:
        return jsonify({'error': 'Site is under maintenance'}), 503

    data = request.json
    user = data.get('user')

    if not user:
        return jsonify({'error': 'User email required'}), 400

    original_length = len(COOKIES_DATA['cookies'])
    COOKIES_DATA['cookies'] = [acc for acc in COOKIES_DATA['cookies'] if acc['user'] != user]
    
    if len(COOKIES_DATA['cookies']) == original_length:
        return jsonify({'error': 'Account not found'}), 404

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
    
    if hashed_password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid password'}), 401

@app.route('/api/admin/maintenance', methods=['POST'])
@admin_required
def toggle_maintenance():
    try:
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        
        return jsonify({
            'success': True,
            'maintenance': MAINTENANCE_MODE
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/stats')
@admin_required
def get_stats():
    try:
        total_accounts = len(COOKIES_DATA['cookies'])
        active_cookies = sum(1 for cookie in COOKIES_DATA['cookies'] if cookie.get('cookie'))
        
        return jsonify({
            'total_accounts': total_accounts,
            'active_cookies': active_cookies,
            'maintenance': MAINTENANCE_MODE
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
