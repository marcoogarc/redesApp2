from flask import Flask, render_template, request, session, redirect, url_for
from sqlalchemy import create_engine, text, func
from werkzeug.security import generate_password_hash, check_password_hash
import config
import os
import requests
import hmac
import hashlib
import base64
from config import FREEPIK_API_KEY, FREEPIK_WEBHOOK_SECRET

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["SESSION_TYPE"] = config.SESSION_TYPE

# Crear engine de BD
engine = create_engine(config.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)

# Subpath de la aplicación
subpath = "redesApp"

# ===== INICIALIZAR BD =====
def init_db():
    """Crea las tablas si no existen"""
    with engine.begin() as conn:  # ← begin() en vez de connect()
        # Crear tabla de películas
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS movies (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                genre VARCHAR(100) NOT NULL,
                year INT NOT NULL,
                rating FLOAT NOT NULL,
                description TEXT,
                poster_url VARCHAR(500) NULL,
                poster_task_id VARCHAR(100) NULL
            )
        """))
        
        # Insertar datos de ejemplo si la tabla está vacía
        result = conn.execute(text("SELECT COUNT(*) as count FROM movies"))
        count = result.fetchone()[0]
        if count == 0:
            movies_data = [
                ("The Shawshank Redemption", "Drama", 1994, 9.3, "Dos hombres en prisión forman una amistad especial."),
                ("The Dark Knight", "Action", 2008, 9.0, "Batman enfrenta al Joker en Gotham."),
                ("Inception", "Sci-Fi", 2010, 8.8, "Un ladrón debe infiltrarse en sueños."),
            ]
            for title, genre, year, rating, desc in movies_data:
                conn.execute(text(
                    "INSERT INTO movies (title, genre, year, rating, description) VALUES (?, ?, ?, ?, ?)",
                    (title, genre, year, rating, desc)
                ))
      
# Inicializar BD al arrancar
try:
    init_db()
except Exception as e:
    print(f"Error inicializando BD: {e}")

FREEPIK_MYSTIC_URL = "https://api.freepik.com/v1/ai/mystic"

def verify_freepik_webhook(req):
    """Verifica la firma HMAC del webhook de Freepik."""
    wid = req.headers.get("webhook-id")
    wts = req.headers.get("webhook-timestamp")
    wsg = req.headers.get("webhook-signature")

    if not (wid and wts and wsg):
        return False

    body = req.get_data(as_text=True)
    content_to_sign = f"{wid}.{wts}.{body}"

    secret_bytes = FREEPIK_WEBHOOK_SECRET.encode()
    hmac_bytes = hmac.new(secret_bytes, content_to_sign.encode(), hashlib.sha256).digest()
    generated_signature = base64.b64encode(hmac_bytes).decode()

    for entry in wsg.split():
        try:
            version, expected = entry.split(",")
            if expected == generated_signature:
                return True
        except ValueError:
            continue
    return False

def start_mystic_poster_task(title, genre):
    """Lanza tarea Mystic y devuelve task_id."""
    prompt = f"Professional cinematic movie poster for film '{title}', {genre} genre, dramatic lighting, high quality, ultra realistic, no text on poster"
    payload = {
        "prompt": prompt,
        "resolution": "2k",
        "aspect_ratio": "portrait_2_3",
        "model": "realism",
        "creative_detailing": 40,
        "engine": "automatic",
        "filter_nsfw": True,
        # CAMBIA ESTO por tu URL pública cuando subas a AlwaysData
        "webhook_url": "https://marcoweb.alwaysdata.net/redesApp/freepik-webhook"

        # "webhook_url": "https://tudominio.alwaysdata.net/redesApp/freepik-webhook"  # PRODUCTION
    }
    headers = {
        "x-freepik-api-key": FREEPIK_API_KEY,
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(FREEPIK_MYSTIC_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            task_id = data.get("data", {}).get("task_id") or data.get("task_id")
            return task_id
    except Exception as e:
        print(f"Error Freepik Mystic: {e}")
    return None


# ===== RUTAS =====
@app.route(f"/{subpath}/")
def index():
    """Página principal con listado de películas"""
    usuario = session.get("usuario")
    user_data = None
    try:
        with engine.connect() as conn:
            if usuario:
                # Obtener datos del usuario (incluyendo puntos y nivel)
                result_user = conn.execute(text("SELECT id, points, level FROM users WHERE username = :u"), {"u": usuario})
                user_data = result_user.fetchone()

            result = conn.execute(text("""
                SELECT m.id,
                       m.title,
                       m.genre,
                       m.year,
                       ROUND(COALESCE(AVG(r.rating), m.rating), 1) AS rating,
                       COUNT(r.id) AS rating_count,
                       m.poster_url,
                       m.poster_task_id
                FROM movies m
                LEFT JOIN ratings r ON r.movie_id = m.id
                GROUP BY m.id, m.title, m.genre, m.year, m.rating, m.poster_url, m.poster_task_id
                ORDER BY m.year DESC
            """))
            movies = [dict(row._mapping) for row in result]
    except Exception as e:
        movies = []
        print(f"Error al obtener películas: {e}")
    
    favoritos = session.get("favoritos", [])
    return render_template(
        "index.html",
        movies=movies,
        usuario=usuario,
        user_data=user_data,
        favoritos=favoritos,
        subpath=subpath
    )

@app.route(f"/{subpath}/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        error = None

        if not username or not password:
            error = "Usuario y contraseña son obligatorios"
        else:
            try:
                with engine.connect() as conn:
                    result = conn.execute(
                        text("SELECT id, username, password_hash FROM users WHERE username = :u"),
                        {"u": username}
                    )
                    row = result.fetchone()
                if not row or not check_password_hash(row.password_hash, password):
                    error = "Usuario o contraseña incorrectos"
                else:
                    session["usuario"] = row.username
                    session["favoritos"] = []
                    return redirect(f"/{subpath}/")
            except Exception as e:
                error = f"Error en login: {e}"

        return render_template("login.html", error=error, subpath=subpath, usuario=None)

    return render_template("login.html", subpath=subpath, usuario=None)

@app.route(f"/{subpath}/register", methods=["GET", "POST"])
def register():
    usuario = session.get("usuario")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        password2 = request.form.get("password2", "").strip()

        error = None

        if not username or not password or not password2:
            error = "Todos los campos obligatorios deben rellenarse"
        elif password != password2:
            error = "Las contraseñas no coinciden"
        else:
            try:
                with engine.connect() as conn:
                    # ¿existe ya el usuario?
                    result = conn.execute(
                        text("SELECT id FROM users WHERE username = :u"),
                        {"u": username}
                    )
                    if result.fetchone():
                        error = "El nombre de usuario ya existe"
                    else:
                        pwd_hash = generate_password_hash(password)
                        conn.execute(
                            text("""
                                INSERT INTO users (username, email, password_hash)
                                VALUES (:u, :e, :p)
                            """),
                            {"u": username, "e": email or None, "p": pwd_hash}
                        )
                        conn.commit()
                        # auto-login tras registro
                        session["usuario"] = username
                        session["favoritos"] = []
                        return redirect(f"/{subpath}/")
            except Exception as e:
                error = f"Error al registrar usuario: {e}"

        return render_template("register.html", error=error, usuario=usuario, subpath=subpath)

    return render_template("register.html", usuario=usuario, subpath=subpath)

@app.route(f"/{subpath}/logout")
def logout():
    """Logout de usuario"""
    session.clear()
    return redirect(f"/{subpath}/")

@app.route(f"/{subpath}/add", methods=["GET", "POST"])
def add_movie():
    """Añadir película con póster AI (solo logueados)."""
    usuario = session.get("usuario")
    if not usuario:
        return redirect(f"/{subpath}/login")
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        genre = request.form.get("genre", "").strip()
        year = request.form.get("year", "")
        rating = request.form.get("rating", "")
        description = request.form.get("description", "").strip()
        
        if title and genre and year and rating:
            try:
                with engine.connect() as conn:
                    # 1. Insertar película sin póster
                    result = conn.execute(text("""
                        INSERT INTO movies (title, genre, year, rating, description, poster_url, poster_task_id)
                        VALUES (:t, :g, :y, :r, :d, NULL, NULL)
                    """), {
                        "t": title, "g": genre, "y": int(year), "r": float(rating), "d": description
                    })
                    movie_id = result.lastrowid

                    # 2. Otorgar puntos al usuario
                    user_res = conn.execute(text("SELECT id, points, level FROM users WHERE username = :u"), {"u": usuario})
                    user_data = user_res.fetchone()
                    if user_data:
                        new_points = user_data.points + 10
                        new_level = user_data.level
                        if new_points >= new_level * 100:
                            new_level += 1
                        conn.execute(text("""
                            UPDATE users SET points = :p, level = :l WHERE id = :uid
                        """), {"p": new_points, "l": new_level, "uid": user_data.id})

                    conn.commit()

                    # 3. Lanzar generación de póster AI (asíncrono)
                    task_id = start_mystic_poster_task(title, genre)
                    if task_id:
                        conn.execute(text("""
                            UPDATE movies SET poster_task_id = :task WHERE id = :id
                        """), {"task": task_id, "id": movie_id})
                        conn.commit()
                        print(f"Película {movie_id}: Mystic task {task_id} iniciada")

                return redirect(f"/{subpath}/")
            except Exception as e:
                error = f"Error al añadir película: {e}"
                return render_template("add_movie.html", error=error, subpath=subpath, usuario=usuario)
        
        error = "Todos los campos obligatorios"
        return render_template("add_movie.html", error=error, subpath=subpath, usuario=usuario)
    
    return render_template("add_movie.html", subpath=subpath, usuario=usuario)

@app.route(f"/{subpath}/search", methods=["GET", "POST"])
def search():
    """Búsqueda por género o título"""
    usuario = session.get("usuario")
    movies = []
    query_type = None
    query_value = None
    
    if request.method == "POST":
        query_type = request.form.get("query_type", "genre")
        query_value = request.form.get("query_value", "").strip()
        
        if query_value:
            try:
                with engine.connect() as conn:
                    if query_type == "genre":
                        result = conn.execute(text("""
                            SELECT m.id, m.title, m.genre, m.year, m.rating, m.poster_url, m.poster_task_id
                            FROM movies m
                            WHERE m.genre LIKE :q
                            ORDER BY m.year DESC
                        """), {"q": f"%{query_value}%"})
                    else:  # title
                        result = conn.execute(text("""
                            SELECT m.id, m.title, m.genre, m.year, m.rating, m.poster_url, m.poster_task_id
                            FROM movies m
                            WHERE m.title LIKE :q
                            ORDER BY m.year DESC
                        """), {"q": f"%{query_value}%"})
                    movies = [dict(row._mapping) for row in result]
            except Exception as e:
                print(f"Error en búsqueda: {e}")
    
    favoritos = session.get("favoritos", [])
    return render_template(
        "search.html", 
        movies=movies, 
        usuario=usuario, 
        query_type=query_type, 
        query_value=query_value, 
        favoritos=favoritos, 
        subpath=subpath
    )

@app.route(f"/{subpath}/favoritos")
def favoritos():
    """Ver películas favoritas"""
    usuario = session.get("usuario")
    if not usuario:
        return redirect(f"/{subpath}/login")
    
    favoritos_ids = session.get("favoritos", [])
    movies = []
    
    if favoritos_ids:
        try:
            with engine.connect() as conn:
                ids_str = ", ".join(map(str, favoritos_ids))
                result = conn.execute(text(f"""
                    SELECT m.id, m.title, m.genre, m.year, m.rating, 
                           m.poster_url, m.poster_task_id
                    FROM movies m
                    WHERE m.id IN ({ids_str})
                    ORDER BY FIELD(m.id, {ids_str})
                """))
                movies = [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error al obtener favoritos: {e}")
    
    return render_template("favoritos.html", movies=movies, usuario=usuario, subpath=subpath)


@app.route(f"/{subpath}/movie/<int:movie_id>")
def movie_detail(movie_id):
    usuario = session.get("usuario")
    favoritos = session.get("favoritos", [])
    comments = []
    movie = None
    has_rated = False

    try:
        with engine.connect() as conn:
            user_id = None
            if usuario:
                result_user = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": usuario})
                user_row = result_user.fetchone()
                if user_row:
                    user_id = user_row.id

            result = conn.execute(text("""
                SELECT m.id, m.title, m.genre, m.year, m.description,
                       ROUND(COALESCE(AVG(r.rating), m.rating), 1) AS rating,
                       COUNT(r.id) AS rating_count,
                       m.poster_url, m.poster_task_id
                FROM movies m
                LEFT JOIN ratings r ON r.movie_id = m.id
                WHERE m.id = :id
                GROUP BY m.id
            """), {"id": movie_id})
            row = result.fetchone()

            if not row:
                movie = None
            else:
                movie = dict(row._mapping)
                result_comments = conn.execute(text("""
                    SELECT r.rating, r.comment, u.username, r.created_at
                    FROM ratings r
                    JOIN users u ON u.id = r.user_id
                    WHERE r.movie_id = :id AND r.comment IS NOT NULL AND r.comment != ''
                    ORDER BY r.created_at DESC
                """), {"id": movie_id})
                comments = [dict(row._mapping) for row in result_comments]

                if user_id:
                    result_rating = conn.execute(
                        text("SELECT id FROM ratings WHERE user_id = :uid AND movie_id = :mid"),
                        {"uid": user_id, "mid": movie_id}
                    )
                    if result_rating.fetchone():
                        has_rated = True
    except Exception as e:
        print(f"Error obteniendo detalle de película: {e}")
        movie = None

    return render_template(
        "movie_detail.html",
        movie=movie,
        comments=comments,
        usuario=usuario,
        favoritos=favoritos,
        has_rated=has_rated,
        subpath=subpath
    )

@app.route(f"/{subpath}/rate/<int:movie_id>", methods=["POST"])
def rate_movie(movie_id):
    usuario = session.get("usuario")
    if not usuario:
        return redirect(f"/{subpath}/login")

    rating_str = request.form.get("rating", "").strip()
    comment = request.form.get("comment", "").strip()

    try:
        rating_val = float(rating_str)
        if not (0 <= rating_val <= 10):
            raise ValueError("Rating out of range")
    except (ValueError, TypeError):
        return redirect(f"/{subpath}/movie/{movie_id}")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": usuario})
            row = result.fetchone()
            if not row:
                return redirect(f"/{subpath}/login")
            user_id = row.id

            conn.execute(text("""
                INSERT IGNORE INTO ratings (user_id, movie_id, rating, comment)
                VALUES (:uid, :mid, :r, :c)
            """), {
                "uid": user_id,
                "mid": movie_id,
                "r": rating_val,
                "c": comment or None
            })
            conn.commit()
    except Exception as e:
        print(f"Error al guardar rating: {e}")

    return redirect(f"/{subpath}/movie/{movie_id}")

@app.route(f"/{subpath}/add_favorito/<int:movie_id>")
def add_favorito(movie_id):
    """Añadir película a favoritos (sesión)"""
    favoritos = session.get("favoritos", [])
    if movie_id not in favoritos:
        favoritos.append(movie_id)
    session["favoritos"] = favoritos
    return redirect(request.referrer or f"/{subpath}/")

@app.route(f"/{subpath}/remove_favorito/<int:movie_id>")
def remove_favorito(movie_id):
    """Quitar película de favoritos"""
    favoritos = session.get("favoritos", [])
    if movie_id in favoritos:
        favoritos.remove(movie_id)
    session["favoritos"] = favoritos
    return redirect(request.referrer or f"/{subpath}/")

@app.route(f"/{subpath}/recomendaciones/<int:movie_id>")
def recomendaciones(movie_id):
    """Sistema inteligente: recomienda películas similares"""
    usuario = session.get("usuario")
    
    try:
        with engine.connect() as conn:
            # Obtener película actual
            result = conn.execute(text("""
                SELECT m.id, m.title, m.genre, m.year, m.rating,
                       m.poster_url, m.poster_task_id
                FROM movies m
                WHERE m.id = :id
            """), {"id": movie_id})
            row = result.fetchone()
            if not row:
                movie = None
                recomendadas = []
            else:
                movie = dict(row._mapping)
                rating_min = movie["rating"] - 1.5
                rating_max = movie["rating"] + 1.5
                result = conn.execute(text("""
                    SELECT m.id, m.title, m.genre, m.year, m.rating,
                           m.poster_url, m.poster_task_id
                    FROM movies m
                    WHERE m.genre = :g
                      AND m.id != :mid
                      AND m.rating BETWEEN :rmin AND :rmax
                    ORDER BY ABS(m.rating - :base_rating), m.year DESC
                    LIMIT 5
                """), {
                    "g": movie["genre"],
                    "mid": movie_id,
                    "rmin": rating_min,
                    "rmax": rating_max,
                    "base_rating": movie["rating"]
                })
                recomendadas = [dict(row._mapping) for row in result]
    except Exception as e:
        movie = None
        recomendadas = []
        print(f"Error en recomendaciones: {e}")
    
    favoritos = session.get("favoritos", [])
    return render_template(
        "recomendaciones.html", 
        movie=movie, 
        recomendadas=recomendadas, 
        usuario=usuario, 
        favoritos=favoritos, 
        subpath=subpath
    )


@app.route(f"/{subpath}/freepik-webhook", methods=["POST"])
def freepik_webhook():
    """Recibe resultados de Freepik Mystic."""
    if not verify_freepik_webhook(request):
        print("Webhook Freepik rechazado: firma inválida")
        return "", 401

    try:
        data = request.get_json(silent=True) or {}
        task_id = data.get("task_id") or data.get("data", {}).get("task_id")
        status = data.get("status") or data.get("data", {}).get("status")
        generated = data.get("generated") or data.get("data", {}).get("generated", [])

        print(f"Freepik webhook: task={task_id}, status={status}, images={len(generated)}")

        if task_id and status == "COMPLETED" and generated:
            poster_url = generated[0]  # primera imagen
            with engine.connect() as conn:
                result = conn.execute(text("""
                    UPDATE movies SET poster_url = :url 
                    WHERE poster_task_id = :task
                """), {"url": poster_url, "task": task_id})
                if result.rowcount > 0:
                    conn.commit()
                    print(f"Póster guardado para task {task_id}: {poster_url}")
                else:
                    print(f"No se encontró película para task {task_id}")

        return "", 200
    except Exception as e:
        print(f"Error webhook Freepik: {e}")
        return "", 500

application = app

# ===== MAIN =====
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
