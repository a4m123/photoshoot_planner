import os
import sqlite3
import base64
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime
from flask import send_from_directory


# --- Пути хранения ---
BASE_DIR = os.path.expanduser('~/photoshoot_planner')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'photoshoot.db')

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Flask App ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Инициализация базы данных ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS project (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS frame (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                description TEXT,
                image_path TEXT,
                character_name TEXT,
                FOREIGN KEY(project_id) REFERENCES project(id)
            )
        ''')

init_db()

# --- Вспомогательные функции ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

# --- Маршруты ---

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute('SELECT * FROM user').fetchall()
    return render_template('index.html', users=users)

@app.route('/create_user', methods=['POST'])
def create_user():
    username = request.form['username']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO user (username) VALUES (?)', (username,))
    return redirect(url_for('index'))

@app.route('/user/<int:user_id>')
def user_projects(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        user = conn.execute('SELECT * FROM user WHERE id=?', (user_id,)).fetchone()
        projects = conn.execute('SELECT * FROM project WHERE user_id=?', (user_id,)).fetchall()
    return render_template('user_projects.html', user=user, projects=projects)

@app.route('/user/<int:user_id>/create_project', methods=['POST'])
def create_project(user_id):
    name = request.form['name']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO project (name, user_id) VALUES (?, ?)', (name, user_id))
    return redirect(url_for('user_projects', user_id=user_id))

@app.route('/project/<int:project_id>')
def view_project(project_id):
    with sqlite3.connect(DB_PATH) as conn:
        project = conn.execute('SELECT * FROM project WHERE id=?', (project_id,)).fetchone()
        frames = conn.execute('SELECT * FROM frame WHERE project_id=?', (project_id,)).fetchall()
    return render_template('project.html', project=project, frames=frames)

@app.route('/project/<int:project_id>/add_frame', methods=['POST'])
def add_frame(project_id):
    description = request.form.get('description', 'Без описания')
    character_name = request.form.get('character_name')
    file = request.files.get('image')
    image_data = request.form.get('image_data')
    filename = None

    if image_data:
        try:
            header, encoded = image_data.split(',', 1)
            data = base64.b64decode(encoded)
            image = Image.open(BytesIO(data))
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'sketch_{timestamp}.png'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(filepath)
        except Exception as e:
            print("Ошибка при сохранении нарисованного эскиза:", e)
    elif file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            INSERT INTO frame (project_id, description, image_path, character_name)
            VALUES (?, ?, ?, ?)''',
            (project_id, description, filename, character_name))
    return redirect(url_for('view_project', project_id=project_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/project/<int:project_id>/frame/<int:frame_id>/rename', methods=['POST'])
def rename_frame(project_id, frame_id):
    new_desc = request.form['new_description']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('UPDATE frame SET description=? WHERE id=?', (new_desc, frame_id))
    return redirect(url_for('view_project', project_id=project_id))

@app.route('/project/<int:project_id>/frame/<int:frame_id>/delete', methods=['POST'])
def delete_frame(project_id, frame_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        image_path = cur.execute('SELECT image_path FROM frame WHERE id=?', (frame_id,)).fetchone()
        if image_path and image_path[0]:
            image_file = os.path.join(app.config['UPLOAD_FOLDER'], image_path[0])
            if os.path.exists(image_file):
                os.remove(image_file)
        cur.execute('DELETE FROM frame WHERE id=?', (frame_id,))
    return redirect(url_for('view_project', project_id=project_id))

# --- Запуск сервера ---
if __name__ == '__main__':
    app.run(debug=True)
