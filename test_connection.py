"""
Script de test pour vérifier la connexion à Supabase.
À exécuter localement après avoir configuré DATABASE_URL dans .env
"""

import os
import psycopg2
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("[ERREUR] DATABASE_URL n'est pas définie.")
    print("Créez un fichier .env à partir de .env.example et configurez DATABASE_URL")
    exit(1)

try:
    print(f"[TEST] Tentative de connexion à la base de données...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"[OK] Connexion réussie !")
    print(f"Version PostgreSQL : {version[0]}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"[ERREUR] Échec de la connexion : {e}")
    exit(1)
