"""
Aurion — Récupération du prix de l'or (PAXG) via l'API publique Binance.

Ce script ne nécessite AUCUN compte Binance : les endpoints utilisés
sont publics (données de marché en lecture seule).

Deux fonctions principales :
  1. bootstrap_historique()  -> remplit la base avec l'historique récent
  2. recuperer_prix_actuel() -> récupère le prix en direct et l'enregistre

Base de données : Supabase (Postgres), une seule table "prix".
"""

import os
import psycopg2
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env (local uniquement)
load_dotenv()

# --- Configuration ---
SYMBOLE = "PAXGUSDT"          # paire or tokenisé / dollar
BASE_URL = "https://api.binance.com"
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Établit une connexion à la base de données Supabase."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL n'est pas définie dans les variables d'environnement")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Crée la table si elle n'existe pas encore."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prix (
            id SERIAL PRIMARY KEY,
            timestamp TEXT NOT NULL,
            prix_usd REAL NOT NULL,
            source TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def recuperer_prix_actuel(max_retries=2):
    """
    Récupère le prix instantané de PAXG/USD.
    Endpoint public, aucune authentification requise.
    Inclut une logique de retry simple en cas d'erreur réseau.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "pax-gold", "vs_currencies": "usd"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for attempt in range(max_retries + 1):
        try:
            reponse = requests.get(url, params=params, headers=headers, timeout=10)
            reponse.raise_for_status()
            donnees = reponse.json()

            prix = float(donnees["pax-gold"]["usd"])
            horodatage = datetime.now(timezone.utc).isoformat()

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO prix (timestamp, prix_usd, source) VALUES (%s, %s, %s)",
                (horodatage, prix, "live"),
            )
            conn.commit()
            cur.close()
            conn.close()

            print(f"[OK] {horodatage} — PAXG/USD = {prix} $")
            return prix

        except (requests.RequestException, psycopg2.Error) as e:
            if attempt < max_retries:
                print(f"[RETRY] Tentative {attempt + 1}/{max_retries} après erreur : {e}")
                continue
            else:
                raise


def bootstrap_historique(intervalle="1h", limite=500):
    """
    Récupère un historique de bougies (klines) pour amorcer la base
    avant de lancer le suivi en direct. Utile pour le backtesting futur.

    intervalle : "1h", "4h", "1d", etc.
    limite     : nombre de bougies (max 1000 côté Binance)
    """
    url = f"{BASE_URL}/api/v3/klines"
    params = {"symbol": SYMBOLE, "interval": intervalle, "limit": limite}
    reponse = requests.get(url, params=params, timeout=10)
    reponse.raise_for_status()
    bougies = reponse.json()

    conn = get_db_connection()
    cur = conn.cursor()
    for bougie in bougies:
        # Format Binance : [open_time, open, high, low, close, volume, ...]
        horodatage = datetime.fromtimestamp(
            bougie[0] / 1000, tz=timezone.utc
        ).isoformat()
        prix_cloture = float(bougie[4])
        cur.execute(
            "INSERT INTO prix (timestamp, prix_usd, source) VALUES (%s, %s, %s)",
            (horodatage, prix_cloture, f"historique_{intervalle}"),
        )
    conn.commit()
    cur.close()
    conn.close()

    print(f"[OK] {len(bougies)} bougies historiques ({intervalle}) enregistrées.")


def afficher_dernieres_lignes(n=5):
    """Affiche les n dernières entrées pour vérifier que tout fonctionne."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT timestamp, prix_usd, source FROM prix ORDER BY id DESC LIMIT %s",
        (n,),
    )
    for ligne in cur.fetchall():
        print(ligne)
    cur.close()
    conn.close()


if __name__ == "__main__":
    import sys

    # Mode d'exécution : "full" (défaut) ou "fetch_only" (pour GitHub Actions)
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    init_db()

    if mode == "fetch_only":
        # Mode GitHub Actions : uniquement récupérer le prix actuel
        try:
            recuperer_prix_actuel()
        except Exception as e:
            print(f"[ERREUR] Échec de la récupération du prix : {e}")
            sys.exit(1)
    else:
        # Mode complet : historique + prix actuel (à exécuter manuellement une fois)
        bootstrap_historique(intervalle="1h", limite=500)
        recuperer_prix_actuel()

        # Vérification
        print("\nDernières lignes en base :")
        afficher_dernieres_lignes()
