from flask import render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from app import app, db
from app.models import User
import os
import shutil
import uuid
from app.utils import load_known_faces, scan_photo_from_memory
import base64

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            session['user_id'] = str(uuid.uuid4())
            session['directories_created'] = False
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Login failed. Check your credentials and try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['user_id'])
    user_known_faces_folder = os.path.join(app.config['KNOWN_FACES_FOLDER'], session['user_id'])
    if os.path.exists(user_upload_folder):
        shutil.rmtree(user_upload_folder)
        app.logger.debug(f"Removed directory: {user_upload_folder}")
    if os.path.exists(user_known_faces_folder):
        shutil.rmtree(user_known_faces_folder)
        app.logger.debug(f"Removed directory: {user_known_faces_folder}")
    session.clear()
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.before_request
def before_request():
    if current_user.is_authenticated:
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
            session['directories_created'] = False
        
        if not session.get('directories_created'):
            user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['user_id'])
            user_known_faces_folder = os.path.join(app.config['KNOWN_FACES_FOLDER'], session['user_id'])
            os.makedirs(user_upload_folder, exist_ok=True)
            os.makedirs(user_known_faces_folder, exist_ok=True)
            app.logger.debug(f"Created directories: {user_upload_folder}, {user_known_faces_folder}")
            session['directories_created'] = True

@app.route('/upload_known_faces', methods=['POST'])
@login_required
def upload_known_faces():
    if 'files[]' not in request.files:
        return redirect(request.url)
    files = request.files.getlist('files[]')
    user_known_faces_folder = os.path.join(app.config['KNOWN_FACES_FOLDER'], session['user_id'])
    for file in files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(user_known_faces_folder, filename)
            file.save(file_path)
            app.logger.debug(f"Saved known face: {file_path}")
    return redirect(url_for('index'))

@app.route('/scan_photos', methods=['POST'])
@login_required
def scan_photos():
    if 'files[]' not in request.files:
        return redirect(request.url)
    files = request.files.getlist('files[]')
    user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['user_id'])
    user_known_faces_folder = os.path.join(app.config['KNOWN_FACES_FOLDER'], session['user_id'])
    
    try:
        known_faces, known_names = load_known_faces(user_known_faces_folder)
    except FileNotFoundError as e:
        known_faces, known_names = [], []
        app.logger.error(e)
    
    results = []
    for file in files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(user_upload_folder, filename)
            file.save(file_path)
            app.logger.debug(f"Saved photo to scan: {file_path}")
            with open(file_path, 'rb') as f:
                file_stream = f.read()
            try:
                matches, image_data = scan_photo_from_memory(file_stream, known_faces, known_names)
                image_data_base64 = base64.b64encode(image_data).decode('utf-8')
                results.append({
                    'file': filename,
                    'matches': matches,
                    'result_image': image_data_base64
                })
            except Exception as e:
                app.logger.error(f"Error scanning photo {filename}: {e}")
                return "Error scanning photo", 500
    return render_template('result.html', results=results)