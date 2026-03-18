from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import json
import os
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'horken_secret_key'

# Configuración de rutas 
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATA_FILE = os.path.join(BASE_DIR, 'eventos_data.json')
USUARIOS = {'admin': 'admin123', 'user1': 'pass123'}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'eventos': []}
    return {'eventos': []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    data = load_data()
    # filtrar
    eventos_lista = [e for e in data.get('eventos', []) if e.get('fecha')]
    events = sorted(eventos_lista, key=lambda x: x['fecha'])
    return render_template('index.html', eventos=events, usuario_logueado='usuario' in session)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user, password = request.form.get('usuario'), request.form.get('password')
        if USUARIOS.get(user) == password:
            session['usuario'] = user
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('index'))

@app.route('/add-event', methods=['GET', 'POST'])
@login_required
def add_event():
    if request.method == 'POST':
        data = load_data()
        files = request.files.getlist('foto_evento')
        filenames = []
        for file in files:
            if file and file.filename != '':
                fn = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                filenames.append(fn)
        
        new_event = {
            'id': int(datetime.now().timestamp()),
            'titulo': request.form.get('titulo'),
            'fecha': request.form.get('fecha'),
            'hora': request.form.get('hora', ''),
            'descripcion': request.form.get('descripcion', ''),
            'ubicacion': request.form.get('ubicacion', ''),
            'noticia': request.form.get('noticia', ''),
            'fotos': filenames,
            'creado_por': session['usuario'],
            'fecha_creacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        data['eventos'].append(new_event)
        save_data(data)
        return redirect(url_for('index'))
    return render_template('add_event.html')

@app.route('/edit-event/<int:event_id>', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    data = load_data()
    event = next((e for e in data['eventos'] if e['id'] == event_id), None)
    if request.method == 'POST' and event:
        for field in ['titulo', 'fecha', 'hora', 'descripcion', 'ubicacion', 'noticia']:
            event[field] = request.form.get(field)
        
        files = request.files.getlist('foto_evento')
        if 'fotos' not in event: event['fotos'] = []
        for file in files:
            if file and file.filename != '':
                fn = secure_filename(f"ed_{int(datetime.now().timestamp())}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                event['fotos'].append(fn)
        save_data(data)
        return redirect(url_for('index'))
    return render_template('edit_event.html', event=event)

@app.route('/delete-photo/<int:event_id>/<filename>')
@login_required
def delete_photo(event_id, filename):
    data = load_data()
    event = next((e for e in data['eventos'] if e['id'] == event_id), None)
    if event and 'fotos' in event and filename in event['fotos']:
        event['fotos'].remove(filename)
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        except: pass
        save_data(data)
    return redirect(url_for('edit_event', event_id=event_id))

@app.route('/delete-event/<int:event_id>')
@login_required
def delete_event(event_id):
    data = load_data()
    data['eventos'] = [e for e in data['eventos'] if e['id'] != event_id]
    save_data(data)
    return redirect(url_for('index'))

@app.template_filter('formato_fecha')
def formato_fecha(f):
    if not f: return ""
    try: return datetime.strptime(f, '%Y-%m-%d').strftime('%B %d, %Y')
    except: return f

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)