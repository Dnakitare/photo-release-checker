from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import io
import base64
import os
from PIL import Image
import numpy as np
from facial_recognition import load_known_faces, scan_photo_from_memory

app = Flask(__name__)
app.config['KNOWN_FACES_FOLDER'] = 'app/known_faces'

# Ensure directories exist
os.makedirs(app.config['KNOWN_FACES_FOLDER'], exist_ok=True)

# Preload known faces and encodings
try:
    known_faces, known_names = load_known_faces(app.config['KNOWN_FACES_FOLDER'])
except FileNotFoundError as e:
    known_faces, known_names = [], []
    app.logger.error(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_known_faces', methods=['POST'])
def upload_known_faces():
    if 'files[]' not in request.files:
        return redirect(request.url)
    files = request.files.getlist('files[]')
    for file in files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['KNOWN_FACES_FOLDER'], filename))
    # Reload known faces after upload
    global known_faces, known_names
    known_faces, known_names = load_known_faces(app.config['KNOWN_FACES_FOLDER'])
    return redirect(url_for('index'))

@app.route('/scan_photos', methods=['POST'])
def scan_photos():
    if 'files[]' not in request.files:
        return redirect(request.url)
    files = request.files.getlist('files[]')
    results = []
    for file in files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_stream = file.stream.read()
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
    return render_template('results.html', results=results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)