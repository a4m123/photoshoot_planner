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
app.config['THUMBNAIL_FOLDER'] = os.path.join(BASE_DIR, 'uploads', 'thumbs')
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.execute('PRAGMA journal_mode=WAL;')  # включаем write-ahead logging
    return conn

# --- Инициализация базы данных ---
def init_db():
    with get_db_connection() as conn:
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
                thumbnail_path TEXT,
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
    with get_db_connection() as conn:
        users = conn.execute('SELECT * FROM user').fetchall()
    return render_template('index.html', users=users)

@app.route('/create_user', methods=['POST'])
def create_user():
    username = request.form['username']
    with get_db_connection() as conn:
        conn.execute('INSERT INTO user (username) VALUES (?)', (username,))
    return redirect(url_for('index'))

@app.route('/user/<int:user_id>')
def user_projects(user_id):
    with get_db_connection() as conn:
        user = conn.execute('SELECT * FROM user WHERE id=?', (user_id,)).fetchone()
        projects = conn.execute('SELECT * FROM project WHERE user_id=?', (user_id,)).fetchall()
    return render_template('user_projects.html', user=user, projects=projects)

@app.route('/user/<int:user_id>/create_project', methods=['POST'])
def create_project(user_id):
    name = request.form['name']
    with get_db_connection() as conn:
        conn.execute('INSERT INTO project (name, user_id) VALUES (?, ?)', (name, user_id))
    return redirect(url_for('user_projects', user_id=user_id))

@app.route('/project/<int:project_id>')
def view_project(project_id):
    with get_db_connection() as conn:
        project = conn.execute('SELECT * FROM project WHERE id=?', (project_id,)).fetchone()
        frames = conn.execute('SELECT * FROM frame WHERE project_id=?', (project_id,)).fetchall()
    return render_template('project.html', project=project, frames=frames)

@app.route('/project/<int:project_id>/add_frame', methods=['POST'])
def add_frame(project_id):
    description = request.form.get('description', 'Без описания')
    character_name = request.form.get('character_name')
    file = request.files.get('image')
    image_data = request.form.get('image_data')
    image_filename = None
    thumb_filename = None

    if image_data:
        # Скетч с canvas
        try:
            header, encoded = image_data.split(',', 1)
            data = base64.b64decode(encoded)
            image = Image.open(BytesIO(data))

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_filename = f'sketch_{timestamp}.png'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image.save(filepath)

            # Миниатюра
            thumb_filename = f"thumb_{image_filename}"
            thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
            image.thumbnail((300, 300), Image.LANCZOS)
            image.save(thumb_path)

        except Exception as e:
            print("Ошибка при сохранении нарисованного эскиза:", e)

    elif file and allowed_file(file.filename):
        # Загруженное изображение
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{name}_{timestamp}{ext}"

        original_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)

        image = Image.open(file)
        image.thumbnail((1280, 1280), Image.LANCZOS)
        image.save(original_path)

        # Миниатюра
        thumb_filename = f"thumb_{image_filename}"
        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
        thumb = image.copy()
        thumb.thumbnail((300, 300), Image.LANCZOS)
        thumb.save(thumb_path)

    # Сохраняем в БД
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO frame (project_id, description, image_path, character_name, thumbnail_path)
            VALUES (?, ?, ?, ?, ?)''',
            (project_id, description, image_filename, character_name, thumb_filename))
        conn.commit()

    return redirect(url_for('view_project', project_id=project_id))

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/project/<int:project_id>/frame/<int:frame_id>/rename', methods=['POST'])
def rename_frame(project_id, frame_id):
    new_desc = request.form['new_description']
    with get_db_connection() as conn:
        conn.execute('UPDATE frame SET description=? WHERE id=?', (new_desc, frame_id))
    return redirect(url_for('view_project', project_id=project_id))

@app.route('/delete_frame/<int:frame_id>', methods=['POST'])
def delete_frame(frame_id):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        c = conn.cursor()
        # получаем путь к изображению
        c.execute('SELECT image_path FROM frame WHERE id=?', (frame_id,))
        row = c.fetchone()
        if row:
            filename = row[0]
            if filename:
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], 'thumb_' + filename)
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                except Exception as e:
                    print(f"Error deleting files: {e}")

        # удаляем кадр из базы
        c.execute('DELETE FROM frame WHERE id=?', (frame_id,))
        conn.commit()

    return redirect(request.referrer or url_for('index'))

@app.route('/project/<int:project_id>/edit_frame/<int:frame_id>', methods=['POST'])
def edit_frame(project_id, frame_id):
    character_name = request.form.get('character_name')
    description = request.form.get('description')

    with get_db_connection() as conn:
        conn.execute('''
            UPDATE frame
            SET character_name = ?, description = ?
            WHERE id = ? AND project_id = ?
        ''', (character_name, description, frame_id, project_id))
        conn.commit()

    return redirect(url_for('view_project', project_id=project_id))


# --- Запуск сервера ---
if __name__ == '__main__':
    app.run(debug=True)
