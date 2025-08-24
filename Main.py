from flask import Flask, render_template, request, jsonify, session, flash
from colorama import Fore, Style, init
import requests, time, os
from pathlib import Path
from werkzeug.utils import secure_filename
import threading

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production!

# Initialize colorama
init(autoreset=True)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'jpg', 'jpeg', 'png', 'mp4', 'mov'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'token_file' not in request.files:
        return jsonify({'error': 'No token file provided'}), 400
    
    # Save token file
    token_file = request.files['token_file']
    if token_file and allowed_file(token_file.filename):
        token_filename = secure_filename('tokens.txt')
        token_path = os.path.join(app.config['UPLOAD_FOLDER'], token_filename)
        token_file.save(token_path)
        session['token_path'] = token_path
    
    # Save tag file if provided
    if 'tag_file' in request.files:
        tag_file = request.files['tag_file']
        if tag_file and allowed_file(tag_file.filename) and tag_file.filename != '':
            tag_filename = secure_filename('tags.txt')
            tag_path = os.path.join(app.config['UPLOAD_FOLDER'], tag_filename)
            tag_file.save(tag_path)
            session['tag_path'] = tag_path
    
    # Save content files based on post type
    post_type = request.form.get('post_type')
    
    if post_type == 'text':
        if 'text_file' not in request.files:
            return jsonify({'error': 'No text file provided for text posts'}), 400
        
        text_file = request.files['text_file']
        if text_file and allowed_file(text_file.filename):
            text_filename = secure_filename('texts.txt')
            text_path = os.path.join(app.config['UPLOAD_FOLDER'], text_filename)
            text_file.save(text_path)
            session['text_path'] = text_path
    
    else:  # photo or video
        if 'media_file' not in request.files:
            return jsonify({'error': 'No media file provided'}), 400
        
        media_file = request.files['media_file']
        if media_file and allowed_file(media_file.filename):
            media_filename = secure_filename('media.txt')
            media_path = os.path.join(app.config['UPLOAD_FOLDER'], media_filename)
            media_file.save(media_path)
            session['media_path'] = media_path
        
        if 'caption_file' not in request.files:
            return jsonify({'error': 'No caption file provided'}), 400
        
        caption_file = request.files['caption_file']
        if caption_file and allowed_file(caption_file.filename):
            caption_filename = secure_filename('captions.txt')
            caption_path = os.path.join(app.config['UPLOAD_FOLDER'], caption_filename)
            caption_file.save(caption_path)
            session['caption_path'] = caption_path
    
    # Store other form data in session
    session['post_type'] = post_type
    session['delay'] = request.form.get('delay', 10)
    
    return jsonify({'success': 'Files uploaded successfully'})

@app.route('/validate_tokens')
def validate_tokens():
    if 'token_path' not in session or not os.path.exists(session['token_path']):
        return jsonify({'error': 'Token file not found'}), 400
    
    with open(session['token_path'], 'r') as f:
        all_tokens = [line.strip() for line in f if line.strip()]
    
    valid_tokens = []
    token_info = []
    
    for i, token in enumerate(all_tokens):
        try:
            r = requests.get(f'https://graph.facebook.com/me?access_token={token}').json()
            if 'id' in r:
                valid_tokens.append(token)
                token_info.append({
                    'index': i+1,
                    'status': 'VALID',
                    'name': r.get('name', 'Unknown')
                })
            else:
                token_info.append({
                    'index': i+1,
                    'status': 'INVALID',
                    'error': r.get('error', {}).get('message', 'Unknown error')
                })
        except Exception as e:
            token_info.append({
                'index': i+1,
                'status': 'INVALID',
                'error': str(e)
            })
    
    session['valid_tokens'] = valid_tokens
    session['token_info'] = token_info
    
    return jsonify({'tokens': token_info, 'valid_count': len(valid_tokens)})

@app.route('/start_posting')
def start_posting():
    if 'valid_tokens' not in session or len(session['valid_tokens']) == 0:
        return jsonify({'error': 'No valid tokens available'}), 400
    
    # Start posting in a background thread
    thread = threading.Thread(target=posting_worker)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': 'Posting started'})

def posting_worker():
    valid_tokens = session.get('valid_tokens', [])
    post_type = session.get('post_type', 'text')
    delay = int(session.get('delay', 10))
    
    # Load tags if available
    tags_list = []
    if 'tag_path' in session and os.path.exists(session['tag_path']):
        with open(session['tag_path'], 'r') as f:
            tags_list = [line.strip() for line in f if line.strip()]
    
    if post_type == 'text':
        # Load text posts
        if 'text_path' not in session or not os.path.exists(session['text_path']):
            return
        
        with open(session['text_path'], 'r') as f:
            text_posts = [line.strip() for line in f if line.strip()]
        
        # Post text content
        token_index = 0
        for text in text_posts:
            token = valid_tokens[token_index % len(valid_tokens)]
            token_index += 1
            
            try:
                r = post_text(token, text, tags_list)
                if 'id' in r.json():
                    print(Fore.GREEN + f"[{time.strftime('%H:%M:%S')}] [TEXT POSTED] {text[:40]}...")
                else:
                    print(Fore.RED + f"[{time.strftime('%H:%M:%S')}] [TEXT ERROR] {r.json()}")
            except Exception as e:
                print(Fore.RED + f"[EXCEPTION TEXT] {str(e)}")
            
            time.sleep(delay)
    
    else:  # photo or video
        # Load media and captions
        if 'media_path' not in session or not os.path.exists(session['media_path']):
            return
        
        if 'caption_path' not in session or not os.path.exists(session['caption_path']):
            return
        
        with open(session['media_path'], 'r') as f:
            media_list = [line.strip() for line in f if line.strip()]
        
        with open(session['caption_path'], 'r') as f:
            caption_list = [line.strip() for line in f if line.strip()]
        
        # Pair media with captions
        media_posts = [{'media_path': m, 'caption': c} for m, c in zip(media_list, caption_list)]
        
        # Post media content
        token_index = 0
        for item in media_posts:
            token = valid_tokens[token_index % len(valid_tokens)]
            token_index += 1
            
            try:
                if post_type == 'photo':
                    r = upload_photo(token, item['media_path'], item['caption'], tags_list)
                    if 'id' in r.json():
                        print(Fore.GREEN + f"[{time.strftime('%H:%M:%S')}] [PHOTO POSTED] {Path(item['media_path']).name}")
                    else:
                        print(Fore.RED + f"[{time.strftime('%H:%M:%S')}] [PHOTO ERROR] {r.json()}")
                else:  # video
                    r = upload_video(token, item['media_path'], item['caption'], tags_list)
                    if 'id' in r.json():
                        print(Fore.GREEN + f"[{time.strftime('%H:%M:%S')}] [VIDEO POSTED] {Path(item['media_path']).name}")
                    else:
                        print(Fore.RED + f"[{time.strftime('%H:%M:%S')}] [VIDEO ERROR] {r.json()}")
            except Exception as e:
                print(Fore.RED + f"[EXCEPTION MEDIA] {str(e)}")
            
            time.sleep(delay)

# Facebook API functions
def post_text(token, message, tags_list):
    url = 'https://graph.facebook.com/me/feed'
    payload = {
        'message': message,
        'privacy': '{"value":"EVERYONE"}',
        'access_token': token
    }
    if tags_list:
        payload['tags'] = ','.join(tags_list)
    return requests.post(url, data=payload)

def upload_photo(token, file_path, caption, tags_list):
    url = 'https://graph.facebook.com/me/photos'
    with open(file_path, 'rb') as file_data:
        files = {'source': file_data}
        payload = {'access_token': token, 'caption': caption}
        if tags_list:
            payload['tags'] = ','.join(tags_list)
        return requests.post(url, data=payload, files=files)

def upload_video(token, file_path, caption, tags_list):
    url = 'https://graph.facebook.com/me/videos'
    with open(file_path, 'rb') as file_data:
        files = {'file': file_data}
        payload = {'access_token': token, 'description': caption}
        if tags_list:
            payload['tags'] = ','.join(tags_list)
        return requests.post(url, data=payload, files=files)

if __name__ == '__main__':
    app.run(debug=True)
