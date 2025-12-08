# Configuración de la base de datos
# Para LOCAL: usa sqlite (no necesita servidor)
# Para ALWAYSDATA: usa MySQL

import os

# OPCIÓN LOCAL (SQLITE) - descomentar esto para probar en tu PC
#SQLALCHEMY_DATABASE_URI = "sqlite:///movies.db"
#SQLALCHEMY_TRACK_MODIFICATIONS = False

# OPCIÓN ALWAYSDATA (MySQL) - descomentar esto cuando subes
DB_USER = "marcoweb"
DB_PASS = "Mgarciafuste777."
DB_HOST = "mysql-marcoweb.alwaysdata.net"
DB_NAME = "marcoweb_bd"
SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = "tu_clave_secreta_super_segura_12345"
SESSION_TYPE = "filesystem"

# Freepik Mystic AI
FREEPIK_API_KEY = "FPSX48c17bd97c49fc1abe4a223c5e816f50"
FREEPIK_WEBHOOK_SECRET = "81cff74f80418683822892dd93491593"
