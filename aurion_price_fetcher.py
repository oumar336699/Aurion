"""
Aurion — Récupération du prix de l'or (PAXG) via l'API publique Binance.

Ce script ne nécessite AUCUN compte Binance : les endpoints utilisés
sont publics (données de marché en lecture seule).

Deux fonctions principales :
  1. bootstrap_historique()  -> remplit la base avec l'historique récent
  2. recuperer_prix_actuel() -> récupère le prix en direct et l'enregistre

Base de données : Supabase (Postgres), une seule table "prix".
"""

import math
import os
from datetime import datetime, timezone

import psycopg2
import requests
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env (local uniquement)
load_dotenv()

# --- Configuration ---
SYMBOLE = "PAXGUSDT"
INTERVALLE_PRIX = "1h"
BASE_URL = "https://api.binance.com"
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Établit une connexion à la base de données Supabase."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL n'est pas définie dans les variables d'environnement")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Crée la table et rend les insertions de bougies idempotentes."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prix (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    prix_usd REAL NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            cur.execute("""
                DELETE FROM prix ancien
                USING prix conserve
                WHERE ancien.timestamp = conserve.timestamp
                  AND ancien.id > conserve.id
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS prix_timestamp_unique
                ON prix (timestamp)
            """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _timestamp_bougie(bougie):
    """Retourne l'heure d'ouverture Binance au format UTC canonique."""
    return datetime.fromtimestamp(bougie[0] / 1000, tz=timezone.utc).isoformat()


def _bougies_cloturees(bougies):
    maintenant_ms = datetime.now(timezone.utc).timestamp() * 1000
    return [bougie for bougie in bougies if int(bougie[6]) < maintenant_ms]


def _enregistrer_bougies(bougies, source):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO prix (timestamp, prix_usd, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (timestamp) DO UPDATE SET
                    prix_usd = EXCLUDED.prix_usd,
                    source = EXCLUDED.source
                """,
                [(_timestamp_bougie(b), float(b[4]), source) for b in bougies],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _derniere_cloture_enregistree():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT timestamp::timestamptz, prix_usd FROM prix
                WHERE source IN ('binance_1h', 'historique_1h')
                ORDER BY timestamp::timestamptz DESC
                LIMIT 1
            """)
            return cur.fetchone()
    finally:
        conn.close()


def _recuperer_bougies_manquantes(url, prochain_debut_ms):
    nombre_bougies = 0
    derniere_bougie = None
    while True:
        params = {"symbol": SYMBOLE, "interval": INTERVALLE_PRIX, "limit": 1000}
        if prochain_debut_ms is not None:
            params["startTime"] = prochain_debut_ms
        else:
            params["limit"] = 3
        reponse = requests.get(url, params=params, timeout=10)
        reponse.raise_for_status()
        bougies = _bougies_cloturees(reponse.json())
        if not bougies:
            break
        _enregistrer_bougies(bougies, f"binance_{INTERVALLE_PRIX}")
        nombre_bougies += len(bougies)
        derniere_bougie = bougies[-1]
        prochain_debut_ms = int(derniere_bougie[0]) + 60 * 60 * 1000
        if len(bougies) < 1000:
            break
    return nombre_bougies, derniere_bougie


def recuperer_prix_actuel(max_retries=2):
    """
    Récupère et enregistre la dernière bougie Binance 1h clôturée.
    Les appels restent publics et les insertions sont idempotentes.
    """
    url = f"{BASE_URL}/api/v3/klines"
    derniere_ligne = _derniere_cloture_enregistree()
    prochain_debut_ms = (
        int(derniere_ligne[0].timestamp() * 1000) + 1
        if derniere_ligne
        else None
    )
    for attempt in range(max_retries + 1):
        try:
            bougies_enregistrees, derniere_bougie = _recuperer_bougies_manquantes(
                url, prochain_debut_ms
            )
            if derniere_bougie is None:
                if derniere_ligne:
                    horodatage = derniere_ligne[0].isoformat()
                    prix = float(derniere_ligne[1])
                    print(
                        f"[OK] Aucune nouvelle clôture — dernière clôture connue "
                        f"{horodatage} : {prix} $"
                    )
                    return prix
                raise ValueError("Binance n'a retourné aucune bougie 1h clôturée")
            bougie = derniere_bougie
            prix = float(bougie[4])
            if not math.isfinite(prix) or prix <= 0:
                raise ValueError(f"Prix Binance invalide : {prix}")
            horodatage = _timestamp_bougie(bougie)
            print(
                f"[OK] {horodatage} — PAXG/USDT clôture 1h = {prix} $ "
                f"({bougies_enregistrees} bougie(s) ajoutée(s)/mise(s) à jour)"
            )
            return prix

        except (requests.RequestException, psycopg2.Error, ValueError) as e:
            if attempt < max_retries:
                print(f"[RETRY] Tentative {attempt + 1}/{max_retries} après erreur : {e}")
                continue
            raise


def bootstrap_historique(intervalle=INTERVALLE_PRIX, limite=5000):
    """
    Récupère un historique de bougies (klines) pour amorcer la base
    avant de lancer le suivi en direct. Utile pour le backtesting futur.

    intervalle : doit être "1h" pour rester cohérent avec le pipeline de signaux.
    limite     : nombre de bougies clôturées à récupérer (max 10000).
    """
    if intervalle != INTERVALLE_PRIX:
        raise ValueError(f"L'intervalle doit être {INTERVALLE_PRIX} pour Aurion")
    if not 1 <= limite <= 10000:
        raise ValueError("La limite doit être comprise entre 1 et 10000")

    url = f"{BASE_URL}/api/v3/klines"
    intervalle_ms = 60 * 60 * 1000
    debut_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - limite * intervalle_ms
    bougies = []
    while len(bougies) < limite:
        params = {
            "symbol": SYMBOLE,
            "interval": intervalle,
            "startTime": debut_ms,
            "limit": min(1000, limite - len(bougies)),
        }
        reponse = requests.get(url, params=params, timeout=10)
        reponse.raise_for_status()
        page = _bougies_cloturees(reponse.json())
        if not page:
            break
        bougies.extend(page)
        prochain_debut_ms = int(page[-1][0]) + intervalle_ms
        if prochain_debut_ms <= debut_ms:
            raise ValueError("Binance n'avance pas dans les pages historiques")
        debut_ms = prochain_debut_ms

    bougies = bougies[-limite:]
    _enregistrer_bougies(bougies, f"binance_{intervalle}")
    print(f"[OK] {len(bougies)} bougies historiques Binance ({intervalle}) enregistrées.")


def afficher_dernieres_lignes(n=5):
    """Affiche les n dernières entrées pour vérifier que tout fonctionne."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT timestamp, prix_usd, source FROM prix ORDER BY timestamp::timestamptz DESC LIMIT %s",
                (n,),
            )
            for ligne in cur.fetchall():
                print(ligne)
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Mode d'exécution : "full" (défaut) ou "fetch_only" (pour GitHub Actions)
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"

    try:
        init_db()
        if mode == "fetch_only":
            recuperer_prix_actuel()
        elif mode == "full":
            bootstrap_historique(intervalle=INTERVALLE_PRIX, limite=5000)
            recuperer_prix_actuel()
            print("\nDernières lignes en base :")
            afficher_dernieres_lignes()
        else:
            raise ValueError("Mode inconnu. Utilisez 'full' ou 'fetch_only'.")
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération du prix : {e}")
        sys.exit(1)
