"""Interface d'exécution des ordres PAXG/USDT, en simulation par défaut."""

import json
import logging
import math
import os

import ccxt
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Passer explicitement à False uniquement après avoir testé le mode simulation.
MODE_SIMULATION = True
SYMBOLE = "PAXG/USDT"
SOLDE_INITIAL_USDT = float(os.environ.get("AURION_SIMULATION_SOLDE_USDT", "10000"))
FRAIS_TAKER = float(os.environ.get("AURION_FRAIS_TAKER", "0.001"))
SLIPPAGE_ESTIME = float(os.environ.get("AURION_SLIPPAGE_ESTIME", "0.0005"))
LIMITE_ORDRE_USDT = float(os.environ.get("AURION_LIMITE_ORDRE_USDT", "100"))

if (
    not math.isfinite(SOLDE_INITIAL_USDT)
    or SOLDE_INITIAL_USDT <= 0
    or not math.isfinite(FRAIS_TAKER)
    or not 0 <= FRAIS_TAKER < 1
    or not math.isfinite(SLIPPAGE_ESTIME)
    or not 0 <= SLIPPAGE_ESTIME < 1
):
    raise ValueError("Configuration de simulation invalide (solde, frais ou slippage)")
if not math.isfinite(LIMITE_ORDRE_USDT) or LIMITE_ORDRE_USDT <= 0:
    raise ValueError("AURION_LIMITE_ORDRE_USDT doit être supérieure à zéro")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("aurion.broker")


def _valider_ordre(sens, quantite):
    if not isinstance(sens, str):
        raise ValueError("Le sens doit être 'achat' ou 'vente'")
    sens = sens.lower()
    try:
        quantite = float(quantite)
    except (TypeError, ValueError) as erreur:
        raise ValueError("La quantité doit être un nombre fini supérieur à zéro") from erreur
    if sens not in ("achat", "vente"):
        raise ValueError("Le sens doit être 'achat' ou 'vente'")
    if not math.isfinite(quantite) or quantite <= 0:
        raise ValueError("La quantité doit être un nombre fini supérieur à zéro")
    return sens, quantite


class Broker:
    """Exécute ou simule des opérations au comptant sur Binance."""

    def __init__(self):
        self.exchange = None

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
                cur.execute("SELECT pg_advisory_xact_lock(814724192)")
                cur.execute("""
                    SELECT id FROM ordres_simules
                    WHERE action = 'initialisation'
                    ORDER BY id ASC
                    LIMIT 1
                """)
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        INSERT INTO ordres_simules (action, details)
                        VALUES ('initialisation', %s::jsonb)
                        """,
                        (json.dumps({"solde_initial_usdt": SOLDE_INITIAL_USDT}),),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _recuperer_etat_simule(cur):
        cur.execute("""
            SELECT details FROM ordres_simules
            WHERE action = 'initialisation'
            ORDER BY id ASC
            LIMIT 1
        """)
        initialisation = cur.fetchone()
        solde_usdt = float(
            initialisation[0].get("solde_initial_usdt", SOLDE_INITIAL_USDT)
            if initialisation
            else SOLDE_INITIAL_USDT
        )
        position_paxg = 0.0
        cur.execute("""
            SELECT details FROM ordres_simules
            WHERE action = 'passer_ordre'
            ORDER BY id ASC
        """)
        for (details,) in cur.fetchall():
            sens = details.get("sens")
            quantite = float(details.get("quantite", 0))
            prix_execution = float(details.get("prix_execution", 0))
            frais = float(details.get("frais_usdt", 0))
            if (
                sens not in ("achat", "vente")
                or not all(math.isfinite(valeur) for valeur in (quantite, prix_execution, frais))
                or quantite <= 0
                or prix_execution <= 0
                or frais < 0
            ):
                raise ValueError(
                    "L'historique contient un ordre simulé invalide ou incomplet; "
                    "la position ne peut pas être reconstruite de façon fiable"
                )
            if sens == "achat" and prix_execution > 0:
                solde_usdt -= quantite * prix_execution + frais
                position_paxg += quantite
            elif sens == "vente" and prix_execution > 0:
                solde_usdt += quantite * prix_execution - frais
                position_paxg -= quantite
            if solde_usdt < -1e-8 or position_paxg < -1e-8:
                raise ValueError("L'historique des ordres simulés produit un solde négatif")
        return solde_usdt, position_paxg

    @staticmethod
    def _recuperer_prix_reference(cur):
        cur.execute("""
            SELECT prix_usd FROM prix
            WHERE source IN ('binance_1h', 'historique_1h')
            ORDER BY timestamp::timestamptz DESC
            LIMIT 1
        """)
        ligne = cur.fetchone()
        if not ligne or not math.isfinite(float(ligne[0])) or float(ligne[0]) <= 0:
            raise ValueError(
                "Aucune clôture Binance 1h disponible pour valoriser la simulation"
            )
        return float(ligne[0])

    def _enregistrer_simulation(self, action, sens=None, quantite=None, details=None):
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
        logger.info(
            "[OK] Simulation — %s (sens=%s, quantite=%s)",
            action,
            sens or "n/a",
            quantite if quantite is not None else "n/a",
        )

    def get_solde(self):
        """Retourne le solde Binance réel ou l'état explicitement simulé."""
        if MODE_SIMULATION:
            conn = self._get_db_connection()
            try:
                with conn.cursor() as cur:
                    solde_usdt, position_paxg = self._recuperer_etat_simule(cur)
                    solde = {
                        "mode": "simulation",
                        "USDT": round(solde_usdt, 8),
                        "PAXG": round(position_paxg, 8),
                    }
            finally:
                conn.close()
            self._enregistrer_simulation("get_solde", details=solde)
            return solde
        return self.exchange.fetch_balance()

    def passer_ordre(self, sens, quantite):
        """Passe un ordre au marché ou enregistre l'ordre sans l'exécuter."""
        sens, quantite = _valider_ordre(sens, quantite)

        if MODE_SIMULATION:
            return self._passer_ordre_simule(sens, quantite)

        return self._passer_ordre_reel(sens, quantite)

    def _passer_ordre_simule(self, sens, quantite):
        conn = self._get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(814724192)")
                solde_usdt, position_paxg = self._recuperer_etat_simule(cur)
                prix_reference = self._recuperer_prix_reference(cur)
                facteur_slippage = 1 + SLIPPAGE_ESTIME if sens == "achat" else 1 - SLIPPAGE_ESTIME
                prix_execution = prix_reference * facteur_slippage
                frais = quantite * prix_execution * FRAIS_TAKER

                if sens == "achat" and quantite * prix_execution + frais > solde_usdt:
                    raise ValueError("Le solde USDT simulé est insuffisant pour cet achat")
                if sens == "vente" and quantite > position_paxg:
                    raise ValueError("La position PAXG simulée est insuffisante pour cette vente")

                ordre = {
                    "mode": "simulation",
                    "symbole": SYMBOLE,
                    "sens": sens,
                    "quantite": quantite,
                    "prix_reference": prix_reference,
                    "prix_execution": prix_execution,
                    "frais_usdt": frais,
                }
                cur.execute(
                    """
                    INSERT INTO ordres_simules (action, sens, quantite, details)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    ("passer_ordre", sens, quantite, json.dumps(ordre)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("[ERREUR] Ordre simulé refusé ou non enregistré")
            raise
        finally:
            conn.close()
        logger.info(
            "[OK] Simulation — %s %s PAXG à %.4f USDT (frais %.4f USDT)",
            sens,
            quantite,
            prix_execution,
            frais,
        )
        return ordre

    def _passer_ordre_reel(self, sens, quantite):
        cote = "buy" if sens == "achat" else "sell"
        dernier_prix = float(self.exchange.fetch_ticker(SYMBOLE)["last"])
        if not math.isfinite(dernier_prix) or dernier_prix <= 0:
            raise ValueError("Binance a retourné un prix invalide")
        if quantite * dernier_prix > LIMITE_ORDRE_USDT:
            raise ValueError(
                f"Ordre refusé : valeur estimée supérieure à la limite de {LIMITE_ORDRE_USDT:.2f} USDT"
            )
        return self.exchange.create_order(SYMBOLE, "market", cote, quantite)

    def get_position(self):
        """Retourne la quantité de PAXG détenue, sans emprunter de fonds."""
        if MODE_SIMULATION:
            conn = self._get_db_connection()
            try:
                with conn.cursor() as cur:
                    _, position = self._recuperer_etat_simule(cur)
            finally:
                conn.close()
            self._enregistrer_simulation("get_position", details={"PAXG": position})
            return position
        solde = self.exchange.fetch_balance()
        return float(solde.get("total", {}).get("PAXG", 0.0) or 0.0)