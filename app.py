import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

app = Flask(__name__)
app.secret_key = "brawl_esports_2026_final_system"

# --- CONFIGURACIÓN DE FIREBASE ---
ruta_base = os.path.dirname(os.path.abspath(__file__))
# Asegúrate de que el nombre del archivo sea exacto
ruta_certificado = os.path.join(ruta_base, "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(ruta_certificado)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://brawl-67616-default-rtdb.firebaseio.com'
    })

# --- MOTOR DE INTELIGENCIA DE MERCADO ---
def calcular_tier_y_valor(copas, ranked):
    p_copas = {"10k+": 1, "20k+": 3, "30k+": 5, "50k+": 10, "80k+": 15, "100k+": 25}
    p_ranked = {"Diamante": 1, "Mitico": 5, "Legendario": 12, "Master": 25, "Pro": 40}
    
    puntos = p_copas.get(copas, 0) + p_ranked.get(ranked, 0)
    
    if puntos >= 60: return "S+", 15000000
    if puntos >= 45: return "S", 8000000
    if puntos >= 30: return "A", 3500000
    if puntos >= 15: return "B", 1200000
    return "C", 450000

# --- RUTAS DE NAVEGACIÓN ---

@app.route('/')
def landing():
    noticias = db.reference('news').get() or {}
    players = db.reference('users/players').get() or {}
    orgs = db.reference('users/orgs').get() or {}
    
    if 'user' in session:
        if session['user'].get('tipo') == 'player': 
            return redirect(url_for('panel_player'))
        if session['user'].get('tipo') == 'org': 
            return redirect(url_for('panel_org'))
            
    return render_template('landing.html', noticias=noticias, players=players, orgs=orgs)

@app.route('/login', methods=['POST'])
def login():
    name = request.form.get('name')
    password = request.form.get('password')
    
    # Buscar en ambas tablas
    p = db.reference(f'users/players/{name}').get()
    o = db.reference(f'users/orgs/{name}').get()
    u = p or o
    
    if u and u.get('password') == password:
        session['user'] = u
        return redirect(url_for('landing'))
    
    flash("Error: Credenciales no válidas", "danger")
    return redirect(url_for('landing'))

# --- REGISTRO ---

@app.route('/registrar/player', methods=['POST'])
def reg_player():
    data = request.form
    roles = data.getlist('roles')[:3]
    tier, valor = calcular_tier_y_valor(data.get('copas'), data.get('ranked'))
    
    player_data = {
        'name': data['name'],
        'password': data['password'],
        'copas': data['copas'],
        'ranked': data['ranked'],
        'roles': roles,
        'tier': tier,
        'valor': int(valor),
        'equipo': 'Libre',
        'display_name': data['name'],
        'tipo': 'player',
        'mvp_count': 0,
        'titulos': [],
        'ofertas': {},
        'notificaciones': []
    }
    db.reference(f'users/players/{data["name"]}').set(player_data)
    flash("Jugador registrado con éxito", "success")
    return redirect('/')

@app.route('/registrar/org', methods=['POST'])
def reg_org():
    data = request.form
    org_data = {
        'name': data['name'],
        'org_name': data['org_name'],
        'tag': data['tag'].upper()[:3],
        'password': data['password'],
        'presupuesto': 10000000,
        'wins': 0,
        'tipo': 'org'
    }
    db.reference(f'users/orgs/{data["name"]}').set(org_data)
    flash("Organización registrada con éxito", "success")
    return redirect('/')

# --- DASHBOARDS ---

@app.route('/dashboard/player')
def panel_player():
    if 'user' not in session or session['user'].get('tipo') != 'player': 
        return redirect('/')
    
    u = db.reference(f'users/players/{session["user"]["name"]}').get()
    players = db.reference('users/players').get() or {}
    scrims = db.reference('scrims').get() or {}
    noticias = db.reference('news').get() or {}
    return render_template('player_dashboard.html', u=u, players=players, scrims=scrims, noticias=noticias)

@app.route('/dashboard/org')
def panel_org():
    if 'user' not in session or session['user'].get('tipo') != 'org': 
        return redirect('/')
    
    org = db.reference(f'users/orgs/{session["user"]["name"]}').get()
    players = db.reference('users/players').get() or {}
    scrims = db.reference('scrims').get() or {}
    torneos = db.reference('tournaments').get() or {}
    noticias = db.reference('news').get() or {}
    return render_template('org_dashboard.html', org=org, players=players, scrims=scrims, torneos=torneos, noticias=noticias)

# --- SISTEMA DE SCRIMS ---

@app.route('/admin/crear_scrim', methods=['POST'])
def admin_crear_scrim():
    nueva_scrim = {
        'apuesta': int(request.form.get('apuesta', 0)),
        'modo': request.form.get('modo', 'Brawl Ball'),
        'equipo1_id': None,
        'equipo1_name': "Vacante",
        'equipo2_id': None,
        'equipo2_name': "Vacante",
        'estado': 'Abierta',
        'fecha': datetime.now().strftime("%d/%m %H:%M")
    }
    db.reference('scrims').push(nueva_scrim)
    return redirect(url_for('admin_panel'))

@app.route('/unirse_scrim/<s_id>/<slot>')
def unirse_scrim(s_id, slot):
    if 'user' not in session or session['user'].get('tipo') != 'org': 
        return redirect('/')
    
    org_name_id = session['user']['name']
    org_data = db.reference(f'users/orgs/{org_name_id}').get()
    scrim_ref = db.reference(f'scrims/{s_id}')
    scrim = scrim_ref.get()

    if not scrim or scrim.get('estado') == 'Cerrada':
        flash("Esta scrim ya no está disponible.")
        return redirect(url_for('panel_org'))

    if org_data.get('presupuesto', 0) < scrim.get('apuesta', 0):
        flash("Presupuesto insuficiente para la apuesta.")
        return redirect(url_for('panel_org'))

    # Evitar que la misma org ocupe ambos slots
    if scrim.get('equipo1_id') == org_name_id or scrim.get('equipo2_id') == org_name_id:
        flash("Ya estás inscrito en esta scrim.")
        return redirect(url_for('panel_org'))

    updates = {}
    if slot == '1' and not scrim.get('equipo1_id'):
        updates = {'equipo1_id': org_name_id, 'equipo1_name': org_data['org_name']}
    elif slot == '2' and not scrim.get('equipo2_id'):
        updates = {'equipo2_id': org_name_id, 'equipo2_name': org_data['org_name']}
    
    if updates:
        scrim_ref.update(updates)
        # Re-check para cerrar si está llena
        s_upd = scrim_ref.get()
        if s_upd.get('equipo1_id') and s_upd.get('equipo2_id'):
            scrim_ref.update({'estado': 'Confirmada'})
        flash("Inscripción exitosa.")
            
    return redirect(url_for('panel_org'))

# --- MERCADO ---

@app.route('/oferta_partidos', methods=['POST'])
def oferta_partidos():
    if 'user' not in session or session['user'].get('tipo') != 'org': 
        return redirect('/')
        
    p_name = request.form.get('player_name')
    org_id = session['user']['name']
    org_data = db.reference(f'users/orgs/{org_id}').get()
    monto = int(request.form.get('monto', 0))
    
    nueva_oferta = {
        'org_id': org_id,
        'org_name': org_data['org_name'],
        'tag': org_data['tag'],
        'monto': monto,
        'estado': 'Pendiente'
    }
    db.reference(f'users/players/{p_name}/ofertas').push(nueva_oferta)
    flash(f"Oferta enviada a {p_name}")
    return redirect(url_for('panel_org'))

@app.route('/responder_oferta/<o_id>/<accion>')
def responder_oferta(o_id, accion):
    if 'user' not in session: return redirect('/')
    
    p_name = session['user']['name']
    p_ref = db.reference(f'users/players/{p_name}')
    oferta_ref = db.reference(f'users/players/{p_name}/ofertas/{o_id}')
    o = oferta_ref.get()
    
    if accion == 'aceptar' and o:
        org_ref = db.reference(f'users/orgs/{o["org_id"]}')
        org = org_ref.get()
        
        if org and org.get('presupuesto', 0) >= o['monto']:
            # Transacción: restar dinero y asignar equipo
            org_ref.update({'presupuesto': org['presupuesto'] - o['monto']})
            p_ref.update({
                'equipo': o['org_name'],
                'display_name': f"{o['tag']} | {p_name}",
                'ofertas': {} # Limpiar otras ofertas al aceptar una
            })
            flash(f"¡Bienvenido a {o['org_name']}!")
        else:
            flash("La organización ya no tiene fondos suficientes.")
    else:
        if o: oferta_ref.delete()
        flash("Oferta rechazada.")
        
    return redirect(url_for('panel_player'))

@app.route('/admin')
def admin_panel():
    # Solo 1 admin según requerimiento guardado
    orgs = db.reference('users/orgs').get() or {}
    players = db.reference('users/players').get() or {}
    noticias = db.reference('news').get() or {}
    scrims = db.reference('scrims').get() or {}
    return render_template('admin.html', orgs=orgs, players=players, noticias=noticias, scrims=scrims)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)