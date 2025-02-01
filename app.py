from flask import Flask, render_template, request, jsonify, session
import os
import httpx
import json
from datetime import datetime
import hashlib
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
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def add_account():
    data = request.json
    user = data.get('user')
    passw = data.get('password')

    if not all([user, passw]):
        return jsonify({'error': 'Invalid input parameters'}), 400

    cookie, uid = generate_cookie(user, passw)
    
    if cookie and uid:
        for existing in COOKIES_DATA['cookies']:
            if existing['user'] == user:
                return jsonify({'error': 'Account already exists'}), 400
        
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
    return jsonify({
        'success': True,
        'accounts': COOKIES_DATA['cookies']
    })

@app.route('/api/delete', methods=['POST'])
def delete_account():
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

@app.route('/api/cookies/view/<user>', methods=['GET'])
def view_cookies(user):
    try:
        for account in COOKIES_DATA['cookies']:
            if account['user'] == user:
                return jsonify({
                    'success': True,
                    'cookies': account['cookie']
                })
        return jsonify({'error': 'Account not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cookies/refresh/all', methods=['POST'])
def refresh_all_cookies():
    try:
        results = {
            'success': [],
            'failed': []
        }
        
        for account in COOKIES_DATA['cookies']:
            try:
                new_cookie, new_uid = generate_cookie(account['user'], account['password'])
                if new_cookie and new_uid and new_cookie != account.get('cookie'):
                    account['cookie'] = new_cookie
                    account['uid'] = new_uid
                    account['last_refresh'] = datetime.now().isoformat()
                    results['success'].append(account['user'])
                else:
                    results['failed'].append(account['user'])
            except Exception:
                results['failed'].append(account['user'])
        
        return jsonify({
            'success': True,
            'message': f"Successfully refreshed {len(results['success'])} cookies",
            'details': f"Failed: {len(results['failed'])}",
            'results': results
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cookies/download', methods=['GET'])
def download_all_cookies():
    try:
        cookies_text = "\n".join([
            account['cookie']
            for account in COOKIES_DATA['cookies']
            if account.get('cookie')
        ])
        
        return jsonify({
            'success': True,
            'cookies': cookies_text
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
