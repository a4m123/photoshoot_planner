

# --- Импорты стандартных библиотек ---
import os
import sqlite3
import base64
from io import BytesIO
from datetime import datetime

# --- Импорты сторонних библиотек ---
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image

# --- Импорты reportlab ---
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm, inch
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether

# --- Регистрация шрифта ---
pdfmetrics.registerFont(TTFont('DejaVuSans', 'photoshoot_planner/static/fonts/DejaVuSans.ttf'))

# --- Пути хранения ---
BASE_DIR = os.path.expanduser('~/photoshoot_planner')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
THUMBNAIL_FOLDER = os.path.join(UPLOAD_FOLDER, 'thumbs')
DB_PATH = os.path.join(BASE_DIR, 'photoshoot.db')
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

# --- Flask app ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAIL_FOLDER'] = THUMBNAIL_FOLDER


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

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
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            description TEXT,
            image_path TEXT,
            character_name TEXT,
            shoot_time TEXT,
            location TEXT,
            position INTEGER DEFAULT 0,
            FOREIGN KEY(project_id) REFERENCES project(id)
        );
        ''')

init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}


# --- Вспомогательная функция для создания миниатюры ---
def create_thumbnail(image, thumb_path, size=(300, 300)):
    thumb = image.copy()
    thumb.thumbnail(size, Image.LANCZOS)
    thumb.save(thumb_path)

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
        frames = conn.execute('SELECT * FROM frame WHERE project_id=? ORDER BY position', (project_id,)).fetchall()
    return render_template('project.html', project=project, frames=frames)

@app.route('/project/<int:project_id>/add_frame', methods=['POST'])
def add_frame(project_id):
    description = request.form.get('description', 'Без описания')
    character_name = request.form.get('character_name')
    file = request.files.get('image')
    image_data = request.form.get('image_data')
    shoot_time = request.form.get('shoot_time')
    location = request.form.get('location')
    image_filename = None
    thumb_filename = None


    if image_data:
        try:
            header, encoded = image_data.split(',', 1)
            data = base64.b64decode(encoded)
            image = Image.open(BytesIO(data))

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            image_filename = f'sketch_{timestamp}.png'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image.save(filepath)

            thumb_filename = f"thumb_{image_filename}"
            thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
            create_thumbnail(image, thumb_path)

        except Exception as e:
            print("Ошибка при сохранении нарисованного эскиза:", e)

    elif file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        image_filename = f"{name}{ext}"

        original_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)

        image = Image.open(file)
        image.thumbnail((1280, 1280), Image.LANCZOS)
        image.save(original_path)

        thumb_filename = f"thumb_{image_filename}"
        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
        create_thumbnail(image, thumb_path)

    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO frame (project_id, description, image_path, character_name, shoot_time, location)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (project_id, description, image_filename, character_name, shoot_time, location))
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

        c.execute('DELETE FROM frame WHERE id=?', (frame_id,))
        conn.commit()

    return redirect(request.referrer or url_for('index'))

@app.route('/project/<int:project_id>/edit_frame/<int:frame_id>', methods=['POST'])
def edit_frame(project_id, frame_id):
    character_name = request.form.get('character_name')
    description = request.form.get('description')
    shoot_time = request.form.get('shoot_time')
    location = request.form.get('location') 

    with get_db_connection() as conn:
        conn.execute('''
            UPDATE frame
            SET character_name = ?, description = ?, shoot_time = ?, location = ?
            WHERE id = ? AND project_id = ?
        ''', (character_name, description, shoot_time, location, frame_id, project_id))
        conn.commit()

    return redirect(url_for('view_project', project_id=project_id))

@app.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
def edit_project(project_id):
    conn = get_db_connection()
    project = conn.execute('SELECT * FROM project WHERE id = ?', (project_id,)).fetchone()
    conn.close()

    if request.method == 'POST':
        new_name = request.form['name']
        conn = get_db_connection()
        conn.execute('UPDATE project SET name = ? WHERE id = ?', (new_name, project_id))
        conn.commit()
        conn.close()
        return redirect(url_for('view_project', project_id=project_id))

    return render_template('edit_project.html', project=project)

@app.route('/project/<int:project_id>/delete', methods=['POST'])
def delete_project(project_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM frame WHERE project_id = ?', (project_id,))
    conn.execute('DELETE FROM project WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/update_frame_order', methods=['POST'])
def update_frame_order():
    data = request.get_json()
    new_order = data.get('order', [])
    if not new_order:
        return jsonify({'error': 'Invalid data'}), 400

    conn = get_db_connection()
    for idx, frame_id in enumerate(new_order):
        conn.execute("UPDATE frame SET position = ? WHERE id = ?", (idx, frame_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

def fit_image(orig_width, orig_height, max_width, max_height):
    ratio = min(max_width / orig_width, max_height / orig_height)
    return orig_width * ratio, orig_height * ratio

@app.route('/project/<int:project_id>/export_pdf')
def export_project_pdf(project_id):
    conn = get_db_connection()
    project = conn.execute('SELECT * FROM project WHERE id = ?', (project_id,)).fetchone()
    frames = conn.execute('SELECT * FROM frame WHERE project_id = ? ORDER BY position', (project_id,)).fetchall()
    conn.close()

    if not project:
        return "Проект не найден", 404

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Cyrillic', fontName='DejaVuSans', fontSize=12, leading=15, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='CyrillicTitle', fontName='DejaVuSans', fontSize=16, leading=20, alignment=TA_LEFT))

    elements.append(Paragraph(f"<b>Проект:</b> {project[1]}", styles['CyrillicTitle']))
    elements.append(Spacer(1, 12))

    for frame in frames:
        description = frame[2]
        character = frame[4] or ''
        shoot_time = frame[5] or ''
        location = frame[6] or ''
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], frame[3])

        frame_block = []
        frame_block.append(Paragraph(f"<b>Кадр:</b> {description}", styles['Cyrillic']))
        if character:
            frame_block.append(Paragraph(f"<b>Персонаж:</b> {character}", styles['Cyrillic']))
        if shoot_time:
            frame_block.append(Paragraph(f"<b>Время:</b> {shoot_time}", styles['Cyrillic']))
        if location:
            frame_block.append(Paragraph(f"<b>Локация:</b> {location}", styles['Cyrillic']))

        if os.path.exists(image_path):
            try:
                img = RLImage(image_path)
                max_width = 7 * inch
                max_height = 7 * inch
                img.drawWidth, img.drawHeight = fit_image(img.imageWidth, img.imageHeight, max_width, max_height)
                frame_block.append(Spacer(1, 6))
                frame_block.append(img)
            except Exception as e:
                frame_block.append(Paragraph(f"[Ошибка изображения: {e}]", styles['Cyrillic']))
        frame_block.append(Spacer(1, 24))

        elements.append(KeepTogether(frame_block))

    doc.build(elements)
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, as_attachment=True, download_name='project_storyboard.pdf', mimetype='application/pdf')

@app.route('/offline.html')
def offline():
    return render_template('offline.html')

# --- Редактирование имени пользователя ---
@app.route('/user/<int:user_id>/edit', methods=['POST'])
def edit_user(user_id):
    new_username = request.form.get('new_username')
    if new_username:
        with get_db_connection() as conn:
            conn.execute('UPDATE user SET username = ? WHERE id = ?', (new_username, user_id))
    return redirect(url_for('index'))

# --- Удаление пользователя ---
@app.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    with get_db_connection() as conn:
        # Удаляем проекты и кадры пользователя
        projects = conn.execute('SELECT id FROM project WHERE user_id = ?', (user_id,)).fetchall()
        for project in projects:
            conn.execute('DELETE FROM frame WHERE project_id = ?', (project[0],))
        conn.execute('DELETE FROM project WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM user WHERE id = ?', (user_id,))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5005, host='0.0.0.0')