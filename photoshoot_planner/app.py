import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from flask import send_from_directory


# --- Настройки путей ---
BASE_DIR = os.path.expanduser('~/photoshoot_planner')
DB_PATH = os.path.join(BASE_DIR, 'photoshoot.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Создание нужных папок ---
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Flask-приложение ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Инициализация базы данных ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS project (
                        id INTEGER PRIMARY KEY,
                        name TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS frame (
                        id INTEGER PRIMARY KEY,
                        project_id INTEGER,
                        description TEXT,
                        image_path TEXT,
                        FOREIGN KEY(project_id) REFERENCES project(id))''')

init_db()

# --- Вспомогательная функция ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Маршруты ---
@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        projects = conn.execute('SELECT * FROM project').fetchall()
    return render_template('index.html', projects=projects)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/create_project', methods=['POST'])
def create_project():
    name = request.form['name']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO project (name) VALUES (?)', (name,))
    return redirect(url_for('index'))

@app.route('/project/<int:project_id>')
def view_project(project_id):
    with sqlite3.connect(DB_PATH) as conn:
        project = conn.execute('SELECT * FROM project WHERE id=?', (project_id,)).fetchone()
        frames = conn.execute('SELECT * FROM frame WHERE project_id=?', (project_id,)).fetchall()
    return render_template('project.html', project=project, frames=frames)

@app.route('/project/<int:project_id>/add_frame', methods=['POST'])
def add_frame(project_id):
    description = request.form['description']
    file = request.files['image']
    filename = None

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO frame (project_id, description, image_path) VALUES (?, ?, ?)',
                     (project_id, description, filename))
    return redirect(url_for('view_project', project_id=project_id))

# --- Запуск сервера ---
if __name__ == '__main__':
    app.run(debug=True)
