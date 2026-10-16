"""Interface d'exécution des ordres PAXG/USDT, en simulation par défaut."""

import json
import logging
import os

import ccxt
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Passer explicitement à False uniquement après avoir testé le mode simulation.
MODE_SIMULATION = True
SYMBOLE = "PAXG/USDT"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("aurion.broker")


class Broker:
    """Exécute ou simule des opérations au comptant sur Binance."""

    def __init__(self):
        self.exchange = None
        self.position_simulee = 0.0

        if not MODE_SIMULATION:
            api_key = os.environ.get("BINANCE_API_KEY")
            api_secret = os.environ.get("BINANCE_API_SECRET")
            if not api_key or not api_secret:
                raise ValueError(
                    "BINANCE_API_KEY et BINANCE_API_SECRET sont requises en mode réel"
                )
            self.exchange = ccxt.binance({
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
        else:
            self._initialiser_table_simulation()

    @staticmethod
    def _get_db_connection():
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL n'est pas définie dans les variables d'environnement")
        return psycopg2.connect(database_url)

    def _initialiser_table_simulation(self):
        conn = self._get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ordres_simules (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        action TEXT NOT NULL,
                        sens TEXT,
                        quantite DOUBLE PRECISION,
                        details JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                """)
                cur.execute("""
                    SELECT COALESCE(SUM(
                        CASE
                            WHEN sens = 'achat' THEN quantite
                            WHEN sens = 'vente' THEN -quantite
                            ELSE 0
                        END
                    ), 0)
                    FROM ordres_simules
                    WHERE action = 'passer_ordre'
                """)
                self.position_simulee = float(cur.fetchone()[0])
            conn.commit()
        finally:
            conn.close()

    def _enregistrer_simulation(self, action, sens=None, quantite=None, details=None):
        logger.info(
            "[OK] Simulation — %s (sens=%s, quantite=%s)",
            action,
            sens or "n/a",
            quantite if quantite is not None else "n/a",
        )
        conn = self._get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ordres_simules (action, sens, quantite, details)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (action, sens, quantite, json.dumps(details or {})),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("[ERREUR] Impossible d'enregistrer l'action simulée")
            raise
        finally:
            conn.close()

    def get_solde(self):
        """Retourne le solde Binance réel ou l'état explicitement simulé."""
        if MODE_SIMULATION:
            solde = {"mode": "simulation", "USDT": 0.0, "PAXG": self.position_simulee}
            self._enregistrer_simulation("get_solde", details=solde)
            return solde
        return self.exchange.fetch_balance()

    def passer_ordre(self, sens, quantite):
        """Passe un ordre au marché ou enregistre l'ordre sans l'exécuter."""
        sens = sens.lower()
        quantite = float(quantite)
        if sens not in ("achat", "vente"):
            raise ValueError("Le sens doit être 'achat' ou 'vente'")
        if quantite <= 0:
            raise ValueError("La quantité doit être supérieure à zéro")

        if MODE_SIMULATION:
            if sens == "vente" and quantite > self.position_simulee:
                raise ValueError("La position simulée est insuffisante pour cette vente")
            variation = quantite if sens == "achat" else -quantite
            self.position_simulee += variation
            ordre = {
                "mode": "simulation",
                "symbole": SYMBOLE,
                "sens": sens,
                "quantite": quantite,
            }
            self._enregistrer_simulation("passer_ordre", sens, quantite, ordre)
            return ordre

        cote = "buy" if sens == "achat" else "sell"
        return self.exchange.create_order(SYMBOLE, "market", cote, quantite)

    def get_position(self):
        """Retourne la quantité de PAXG détenue, sans emprunter de fonds."""
        if MODE_SIMULATION:
            position = self.position_simulee
            self._enregistrer_simulation(
                "get_position", details={"PAXG": position}
            )
            return position
        solde = self.exchange.fetch_balance()
        return float(solde.get("total", {}).get("PAXG", 0.0) or 0.0)