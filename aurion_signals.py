"""
Aurion — Calcul des indicateurs techniques et génération de signaux.

Les prix sont lus depuis la table "prix" de Supabase et les signaux
calculés sont enregistrés dans la table "signaux".

Modes disponibles :
  1. backtest   -> recalcule les signaux sur tout l'historique
  2. fetch_only -> calcule et enregistre uniquement le dernier signal
    3. entrainer  -> entraîne le modèle sur les signaux historiques
"""

import os
import sys

import pandas as pd
import psycopg2
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env (local uniquement)
load_dotenv()

# --- Configuration ---
DATABASE_URL = os.environ.get("DATABASE_URL")
PERIODE_COURTE = 10
PERIODE_LONGUE = 30
PERIODE_RSI = 14
PERIODE_VOLATILITE = 10
HISTORIQUE_LIVE = PERIODE_LONGUE + 1
HORIZON_PREDICTION = 5
NB_EXEMPLES_MINIMUM = 5
FICHIER_MODELE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modele_aurion.pkl")
FEATURES_MODELE = ["rsi", "ecart_moyennes_pct", "volatilite"]


def get_db_connection():
    """Établit une connexion à la base de données Supabase."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL n'est pas définie dans les variables d'environnement")
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Crée la table des signaux si elle n'existe pas encore."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signaux (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                signal TEXT NOT NULL CHECK (signal IN ('ACHAT', 'VENTE', 'ATTENTE')),
                prix_au_moment REAL NOT NULL,
                moyenne_courte REAL,
                moyenne_longue REAL,
                rsi REAL,
                confiance REAL
            )
        """)
        cur.execute("ALTER TABLE signaux ADD COLUMN IF NOT EXISTS confiance REAL")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def recuperer_prix(limite=None):
    """Récupère les prix dans l'ordre d'insertion, du plus ancien au plus récent."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if limite:
            cur.execute(
                "SELECT timestamp, prix_usd FROM prix ORDER BY id DESC LIMIT %s",
                (limite,),
            )
            lignes = list(reversed(cur.fetchall()))
        else:
            cur.execute("SELECT timestamp, prix_usd FROM prix ORDER BY id ASC")
            lignes = cur.fetchall()
        cur.close()
        return pd.DataFrame(lignes, columns=["timestamp", "prix_usd"])
    finally:
        conn.close()


def calculer_indicateurs(prix):
    """Calcule les moyennes mobiles, le RSI et le signal pour chaque prix."""
    donnees = prix.copy()
    series_prix = donnees["prix_usd"].astype(float)

    donnees["moyenne_courte"] = series_prix.rolling(PERIODE_COURTE).mean()
    donnees["moyenne_longue"] = series_prix.rolling(PERIODE_LONGUE).mean()
    donnees["ecart_moyennes_pct"] = (
        (donnees["moyenne_courte"] - donnees["moyenne_longue"])
        / donnees["moyenne_longue"]
        * 100
    )
    donnees["volatilite"] = series_prix.rolling(PERIODE_VOLATILITE).std()

    variations = series_prix.diff()
    gains = variations.clip(lower=0)
    pertes = -variations.clip(upper=0)
    gain_moyen = gains.rolling(PERIODE_RSI).mean()
    perte_moyenne = pertes.rolling(PERIODE_RSI).mean()
    force_relative = gain_moyen / perte_moyenne
    donnees["rsi"] = 100 - (100 / (1 + force_relative))
    donnees.loc[(perte_moyenne == 0) & (gain_moyen > 0), "rsi"] = 100
    donnees.loc[(perte_moyenne == 0) & (gain_moyen == 0), "rsi"] = 50

    croisement_hausse = (
        (donnees["moyenne_courte"] > donnees["moyenne_longue"])
        & (donnees["moyenne_courte"].shift(1) <= donnees["moyenne_longue"].shift(1))
        & (donnees["rsi"] < 70)
    )
    croisement_baisse = (
        (donnees["moyenne_courte"] < donnees["moyenne_longue"])
        & (donnees["moyenne_courte"].shift(1) >= donnees["moyenne_longue"].shift(1))
        & (donnees["rsi"] > 30)
    )
    donnees["signal"] = "ATTENTE"
    donnees.loc[croisement_hausse, "signal"] = "ACHAT"
    donnees.loc[croisement_baisse, "signal"] = "VENTE"
    return donnees


def convertir_valeur(valeur):
    """Convertit une valeur d'indicateur en nombre SQL ou NULL."""
    return float(valeur) if pd.notna(valeur) else None


def preparer_exemples(donnees):
    """Construit les features et les résultats connus à cinq périodes."""
    exemples = donnees.loc[donnees["signal"].isin(["ACHAT", "VENTE"])].copy()
    prix_futur = donnees["prix_usd"].shift(-HORIZON_PREDICTION)
    prix_futur = prix_futur.reindex(exemples.index).astype(float)
    prix_actuel = exemples["prix_usd"].astype(float)
    exemples["resultat"] = (
        ((exemples["signal"] == "ACHAT") & (prix_futur > prix_actuel))
        | ((exemples["signal"] == "VENTE") & (prix_futur < prix_actuel))
    ).astype(int)
    exemples = exemples.loc[prix_futur.notna()]
    exemples = exemples.replace([float("inf"), float("-inf")], pd.NA)
    return exemples.dropna(subset=FEATURES_MODELE + ["resultat"])


def ajouter_confiance(donnees, modele=None):
    """Ajoute la probabilité de succès du modèle, ou NULL si indisponible."""
    resultat = donnees.copy()
    resultat["confiance"] = None
    if modele is None:
        return resultat

    candidats = resultat["signal"].isin(["ACHAT", "VENTE"])
    features = resultat.loc[candidats, FEATURES_MODELE].replace(
        [float("inf"), float("-inf")], pd.NA
    )
    valides = features.notna().all(axis=1)
    if not valides.any():
        return resultat

    probabilites = modele.predict_proba(features.loc[valides])
    classes = list(modele.classes_)
    if 1 not in classes:
        confiance = [0.0] * len(probabilites)
    else:
        confiance = probabilites[:, classes.index(1)]
    resultat.loc[features.loc[valides].index, "confiance"] = confiance
    return resultat


def charger_modele():
    """Charge le modèle local s'il existe et peut être utilisé."""
    if not os.path.exists(FICHIER_MODELE):
        return None
    try:
        return joblib.load(FICHIER_MODELE)
    except Exception as erreur:
        print(f"[ERREUR] Modèle inutilisable : {erreur}")
        return None


def enregistrer_signaux(donnees, remplacer=False):
    """Enregistre les signaux calculés, avec remplacement optionnel de l'historique."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        donnees = donnees.copy()
        if "confiance" not in donnees.columns:
            donnees["confiance"] = None
        if remplacer:
            cur.execute("DELETE FROM signaux")

        lignes = [
            (
                ligne.timestamp,
                ligne.signal,
                float(ligne.prix_usd),
                convertir_valeur(ligne.moyenne_courte),
                convertir_valeur(ligne.moyenne_longue),
                convertir_valeur(ligne.rsi),
                convertir_valeur(ligne.confiance),
            )
            for ligne in donnees.itertuples(index=False)
        ]
        if lignes:
            cur.executemany(
                """
                INSERT INTO signaux
                    (timestamp, signal, prix_au_moment, moyenne_courte, moyenne_longue, rsi, confiance)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                lignes,
            )
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def lancer_backtest():
    """Recalcule et enregistre les signaux sur tout l'historique des prix."""
    donnees = ajouter_confiance(calculer_indicateurs(recuperer_prix()), charger_modele())
    enregistrer_signaux(donnees, remplacer=True)
    resume = donnees["signal"].value_counts()
    print(
        "[OK] Backtest terminé : "
        f"{resume.get('ACHAT', 0)} ACHAT, "
        f"{resume.get('VENTE', 0)} VENTE, "
        f"{resume.get('ATTENTE', 0)} ATTENTE générés."
    )


def lancer_live():
    """Calcule et enregistre uniquement le signal correspondant au dernier prix."""
    prix = recuperer_prix(limite=HISTORIQUE_LIVE)
    if prix.empty:
        raise ValueError("Aucun prix disponible dans la table prix")

    dernier_signal = ajouter_confiance(calculer_indicateurs(prix), charger_modele()).tail(1)
    enregistrer_signaux(dernier_signal)
    ligne = dernier_signal.iloc[0]
    print(
        f"[OK] {ligne['timestamp']} — Signal : {ligne['signal']} "
        f"(prix : {ligne['prix_usd']} $)"
    )


def lancer_entrainement():
    """Entraîne et sauvegarde le modèle à partir des résultats historiques connus."""
    donnees = calculer_indicateurs(recuperer_prix())
    exemples = preparer_exemples(donnees)
    nombre_exemples = len(exemples)
    if nombre_exemples < NB_EXEMPLES_MINIMUM:
        print(
            "[OK] Entraînement ignoré : "
            f"{nombre_exemples} exemple(s) disponible(s), "
            f"{NB_EXEMPLES_MINIMUM} requis au minimum."
        )
        return

    features = exemples[FEATURES_MODELE]
    cible = exemples["resultat"]
    features_entrainement, features_test, cible_entrainement, cible_test = train_test_split(
        features, cible, test_size=0.2, random_state=42
    )
    evaluation = RandomForestClassifier(n_estimators=100, min_samples_leaf=2, max_features="sqrt", random_state=42)
    evaluation.fit(features_entrainement, cible_entrainement)
    precision = accuracy_score(cible_test, evaluation.predict(features_test))

    modele = RandomForestClassifier(n_estimators=100, min_samples_leaf=2, max_features="sqrt", random_state=42)
    modele.fit(features, cible)
    joblib.dump(modele, FICHIER_MODELE)
    print(
        f"[OK] Modèle entraîné : {nombre_exemples} exemple(s), "
        f"précision sur le jeu de test (20 %) : {precision:.2%}."
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"

    try:
        init_db()
        if mode == "backtest":
            lancer_backtest()
        elif mode == "fetch_only":
            lancer_live()
        elif mode == "entrainer":
            lancer_entrainement()
        else:
            raise ValueError(
                f"Mode inconnu : {mode}. Utilisez 'backtest', 'fetch_only' ou 'entrainer'."
            )
    except Exception as e:
        print(f"[ERREUR] Échec du calcul des signaux : {e}")
        sys.exit(1)