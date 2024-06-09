from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import os
from facial_recognition import load_known_faces, scan_photo

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['RESULTS_FOLDER'] = 'static/results'
app.config['KNOWN_FACES_DIR'] = 'known_faces'

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
            file.save(os.path.join(app.config['KNOWN_FACES_DIR'], filename))
    return redirect(url_for('index'))

@app.route('/scan_photos', methods=['POST'])
def scan_photos():
    if 'files[]' not in request.files:
        return redirect(request.url)
    files = request.files.getlist('files[]')
    known_faces, known_names = load_known_faces(app.config['KNOWN_FACES_DIR'])
    results = []
    for file in files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            matches_found, output_path = scan_photo(file_path, known_faces, known_names)
            results.append({'file': file_path, 'matches': matches_found, 'result_image': output_path})
    return render_template('results.html', results=results)

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=5000)