from flask import Flask, render_template, request, redirect, url_for
import requests, os, time
from pathlib import Path
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = "uploads"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ----------------- Posting Functions -----------------
def validate_tokens(tokens):
    valid = []
    logs = []
    for i, token in enumerate(tokens):
        try:
            r = requests.get(f'https://graph.facebook.com/me?access_token={token}').json()
            if 'id' in r:
                logs.append(f"[{i+1}] ✅ VALID: {r.get('name')}")
                valid.append(token)
            else:
                logs.append(f"[{i+1}] ❌ INVALID: {r.get('error', {}).get('message', 'Unknown error')}")
        except Exception as e:
            logs.append(f"[{i+1}] ❌ INVALID: {str(e)}")
    return valid, logs

def post_text(token, message, tags):
    url = 'https://graph.facebook.com/me/feed'
    payload = {'message': message, 'privacy': '{"value":"EVERYONE"}', 'access_token': token}
    if tags: payload['tags'] = tags
    return requests.post(url, data=payload)

def upload_photo(token, file_path, caption, tags):
    url = 'https://graph.facebook.com/me/photos'
    with open(file_path, 'rb') as f:
        files = {'source': f}
        payload = {'access_token': token, 'caption': caption}
        if tags: payload['tags'] = tags
        return requests.post(url, data=payload, files=files)

def upload_video(token, file_path, caption, tags):
    url = 'https://graph.facebook.com/me/videos'
    with open(file_path, 'rb') as f:
        files = {'file': f}
        payload = {'access_token': token, 'description': caption}
        if tags: payload['tags'] = tags
        return requests.post(url, data=payload, files=files)

# ----------------- Routes -----------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Save uploaded files
        token_file = request.files["token_file"]
        token_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(token_file.filename))
        token_file.save(token_path)

        tokens = [line.strip() for line in open(token_path) if line.strip()]

        tags_file = request.files.get("tags_file")
        tags = []
        if tags_file and tags_file.filename:
            tags_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(tags_file.filename))
            tags_file.save(tags_path)
            tags = [line.strip() for line in open(tags_path) if line.strip()]

        post_type = request.form.get("post_type")
        delay = int(request.form.get("delay", "5"))

        logs = []
        valid_tokens, val_logs = validate_tokens(tokens)
        logs.extend(val_logs)

        if not valid_tokens:
            logs.append("❌ No valid tokens found. Exiting.")
            return render_template("result.html", logs=logs)

        # Text posts
        if post_type == "text":
            text_file = request.files["text_file"]
            text_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(text_file.filename))
            text_file.save(text_path)
            text_posts = [line.strip() for line in open(text_path) if line.strip()]

            for text in text_posts:
                token = valid_tokens[0]  # Round robin logic skip for simplicity
                try:
                    r = post_text(token, text, tags)
                    if 'id' in r.json():
                        logs.append(f"✅ [TEXT POSTED] {text[:40]}...")
                    else:
                        logs.append(f"❌ [TEXT ERROR] {r.json()}")
                except Exception as e:
                    logs.append(f"⚠️ [EXCEPTION TEXT] {str(e)}")
                time.sleep(delay)

        # Photo/Video
        else:
            media_file = request.files["media_file"]
            caption_file = request.files["caption_file"]

            media_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(media_file.filename))
            caption_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(caption_file.filename))
            media_file.save(media_path)
            caption_file.save(caption_path)

            media_list = [line.strip() for line in open(media_path) if line.strip()]
            caption_list = [line.strip() for line in open(caption_path) if line.strip()]

            for m, c in zip(media_list, caption_list):
                token = valid_tokens[0]
                try:
                    if post_type == "photo":
                        r = upload_photo(token, m, c, tags)
                        if 'id' in r.json():
                            logs.append(f"✅ [PHOTO POSTED] {Path(m).name}")
                        else:
                            logs.append(f"❌ [PHOTO ERROR] {r.json()}")
                    else:
                        r = upload_video(token, m, c, tags)
                        if 'id' in r.json():
                            logs.append(f"✅ [VIDEO POSTED] {Path(m).name}")
                        else:
                            logs.append(f"❌ [VIDEO ERROR] {r.json()}")
                except Exception as e:
                    logs.append(f"⚠️ [EXCEPTION MEDIA] {str(e)}")
                time.sleep(delay)

        return render_template("result.html", logs=logs)

    return render_template("index.html")
