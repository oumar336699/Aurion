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
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env (local uniquement)
load_dotenv()

# --- Configuration ---
DATABASE_URL = os.environ.get("DATABASE_URL")
PERIODE_COURTE = 10
PERIODE_LONGUE = 30
PERIODE_RSI = 14
PERIODE_VOLATILITE = 10
INTERVALLE_HEURES = 1
HISTORIQUE_LIVE = PERIODE_LONGUE + 1
HORIZON_PREDICTION = 5
NB_EXEMPLES_MINIMUM = 50
NB_EXEMPLES_TEST_MINIMUM = 10
FRAIS_TAKER = float(os.environ.get("AURION_FRAIS_TAKER", "0.001"))
SLIPPAGE_ESTIME = float(os.environ.get("AURION_SLIPPAGE_ESTIME", "0.0005"))
FICHIER_MODELE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modele_aurion.pkl")
FEATURES_MODELE = ["rsi", "ecart_moyennes_pct", "volatilite"]

if not 0 <= FRAIS_TAKER < 1 or not 0 <= SLIPPAGE_ESTIME < 1:
    raise ValueError("AURION_FRAIS_TAKER et AURION_SLIPPAGE_ESTIME doivent être dans [0, 1)")


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
        cur.execute("""
            DELETE FROM signaux ancien
            USING signaux conserve
            WHERE ancien.timestamp = conserve.timestamp
              AND ancien.id > conserve.id
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS signaux_timestamp_unique
            ON signaux (timestamp)
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def recuperer_prix(limite=None):
    """Récupère uniquement les clôtures horaires Binance dans l'ordre chronologique."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if limite:
            cur.execute(
                """
                SELECT timestamp, prix_usd FROM prix
                WHERE source IN ('binance_1h', 'historique_1h')
                ORDER BY timestamp::timestamptz DESC LIMIT %s
                """,
                (limite,),
            )
            lignes = list(reversed(cur.fetchall()))
        else:
            cur.execute("""
                SELECT timestamp, prix_usd FROM prix
                WHERE source IN ('binance_1h', 'historique_1h')
                ORDER BY timestamp::timestamptz ASC
            """)
            lignes = cur.fetchall()
        cur.close()
        return pd.DataFrame(lignes, columns=["timestamp", "prix_usd"])
    finally:
        conn.close()


def calculer_indicateurs(prix):
    """Calcule les indicateurs séparément sur chaque séquence horaire continue."""
    if prix.empty:
        raise ValueError("Aucun prix Binance horaire disponible")

    donnees = prix.copy()
    donnees["timestamp_dt"] = pd.to_datetime(donnees["timestamp"], utc=True, errors="coerce")
    if donnees["timestamp_dt"].isna().any():
        raise ValueError("Un ou plusieurs horodatages de prix sont invalides")
    donnees = donnees.sort_values("timestamp_dt").drop_duplicates("timestamp_dt", keep="last")
    donnees["segment_id"] = (
        donnees["timestamp_dt"].diff()
        .ne(pd.Timedelta(hours=INTERVALLE_HEURES))
        .cumsum()
    )

    segments_calcules = []
    for _, segment in donnees.groupby("segment_id", sort=False):
        segment = segment.copy()
        series_prix = segment["prix_usd"].astype(float)
        segment["moyenne_courte"] = series_prix.rolling(PERIODE_COURTE).mean()
        segment["moyenne_longue"] = series_prix.rolling(PERIODE_LONGUE).mean()
        segment["ecart_moyennes_pct"] = (
            (segment["moyenne_courte"] - segment["moyenne_longue"])
            / segment["moyenne_longue"]
            * 100
        )
        segment["volatilite"] = series_prix.rolling(PERIODE_VOLATILITE).std()

        variations = series_prix.diff()
        gains = variations.clip(lower=0)
        pertes = -variations.clip(upper=0)
        gain_moyen = gains.rolling(PERIODE_RSI).mean()
        perte_moyenne = pertes.rolling(PERIODE_RSI).mean()
        force_relative = gain_moyen / perte_moyenne
        segment["rsi"] = 100 - (100 / (1 + force_relative))
        segment.loc[(perte_moyenne == 0) & (gain_moyen > 0), "rsi"] = 100
        segment.loc[(perte_moyenne == 0) & (gain_moyen == 0), "rsi"] = 50

        croisement_hausse = (
            (segment["moyenne_courte"] > segment["moyenne_longue"])
            & (segment["moyenne_courte"].shift(1) <= segment["moyenne_longue"].shift(1))
            & (segment["rsi"] < 70)
        )
        croisement_baisse = (
            (segment["moyenne_courte"] < segment["moyenne_longue"])
            & (segment["moyenne_courte"].shift(1) >= segment["moyenne_longue"].shift(1))
            & (segment["rsi"] > 30)
        )
        segment["signal"] = "ATTENTE"
        segment.loc[croisement_hausse, "signal"] = "ACHAT"
        segment.loc[croisement_baisse, "signal"] = "VENTE"
        segments_calcules.append(segment)

    return pd.concat(segments_calcules).sort_values("timestamp_dt").reset_index(drop=True)


def convertir_valeur(valeur):
    """Convertit une valeur d'indicateur en nombre SQL ou NULL."""
    return float(valeur) if pd.notna(valeur) else None


def preparer_exemples(donnees):
    """Construit les features et les résultats connus à cinq périodes."""
    exemples = donnees.loc[donnees["signal"].isin(["ACHAT", "VENTE"])].copy()
    prix_futur = donnees.groupby("segment_id")["prix_usd"].shift(-HORIZON_PREDICTION)
    horodatage_futur = donnees.groupby("segment_id")["timestamp_dt"].shift(-HORIZON_PREDICTION)
    prix_futur = prix_futur.reindex(exemples.index).astype(float)
    horodatage_futur = horodatage_futur.reindex(exemples.index)
    prix_actuel = exemples["prix_usd"].astype(float)
    exemples["date_resultat"] = horodatage_futur
    exemples["resultat"] = (
        ((exemples["signal"] == "ACHAT") & (prix_futur > prix_actuel))
        | ((exemples["signal"] == "VENTE") & (prix_futur < prix_actuel))
    ).astype(int)
    exemples = exemples.loc[prix_futur.notna() & horodatage_futur.notna()]
    exemples = exemples.replace([float("inf"), float("-inf")], float("nan"))
    return exemples.dropna(subset=FEATURES_MODELE + ["resultat"])


def ajouter_confiance(donnees, modele=None):
    """Ajoute la probabilité de succès du modèle, ou NULL si indisponible."""
    resultat = donnees.copy()
    resultat["confiance"] = None
    if modele is None:
        return resultat

    candidats = resultat["signal"].isin(["ACHAT", "VENTE"])
    features = resultat.loc[candidats, FEATURES_MODELE].replace(
        [float("inf"), float("-inf")], float("nan")
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


def ajouter_confiance_walk_forward(donnees):
    """Estime chaque confiance avec les seules étiquettes déjà connues à cette date."""
    resultat = donnees.copy()
    resultat["confiance"] = None
    exemples = preparer_exemples(resultat)
    candidats = resultat.loc[resultat["signal"].isin(["ACHAT", "VENTE"])]

    periodes = candidats["timestamp_dt"].dt.strftime("%Y-%m")
    for periode, signaux_periode in candidats.groupby(periodes, sort=True):
        debut_periode = signaux_periode["timestamp_dt"].min()
        historique = exemples.loc[exemples["date_resultat"] < debut_periode]
        if len(historique) < NB_EXEMPLES_MINIMUM or historique["resultat"].nunique() < 2:
            continue
        modele = creer_modele()
        modele.fit(historique[FEATURES_MODELE], historique["resultat"])
        signaux_scores = ajouter_confiance(signaux_periode, modele)
        resultat.loc[signaux_periode.index, "confiance"] = signaux_scores["confiance"]
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
                ON CONFLICT (timestamp) DO UPDATE SET
                    signal = EXCLUDED.signal,
                    prix_au_moment = EXCLUDED.prix_au_moment,
                    moyenne_courte = EXCLUDED.moyenne_courte,
                    moyenne_longue = EXCLUDED.moyenne_longue,
                    rsi = EXCLUDED.rsi,
                    confiance = EXCLUDED.confiance
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
    """Évalue les signaux sur historique, avec validation walk-forward et coûts."""
    donnees = ajouter_confiance_walk_forward(calculer_indicateurs(recuperer_prix()))
    enregistrer_signaux(donnees, remplacer=True)
    resume = donnees["signal"].value_counts()
    performance = simuler_backtest(donnees)
    print(
        "[OK] Backtest terminé : "
        f"{resume.get('ACHAT', 0)} ACHAT, "
        f"{resume.get('VENTE', 0)} VENTE, "
        f"{resume.get('ATTENTE', 0)} ATTENTE; "
        f"rendement net {performance['rendement_net_pct']:.2f} %, "
        f"drawdown max {performance['drawdown_max_pct']:.2f} %, "
        f"{performance['nombre_trades']} trade(s), "
        f"taux de réussite {performance['taux_reussite_pct']:.1f} % "
        f"(frais {FRAIS_TAKER:.2%}/côté, slippage {SLIPPAGE_ESTIME:.2%}/côté)."
    )
    print(
        "[OK] Références sur la même période : "
        f"achat-conservation net {performance['achat_conservation_pct']:.2f} %, "
        "aucun trade 0.00 %."
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

    exemples = exemples.sort_values("timestamp_dt").reset_index(drop=True)
    separateur = int(len(exemples) * 0.8)
    debut_test = exemples.loc[separateur, "timestamp_dt"]
    entrainement = exemples.loc[exemples["date_resultat"] < debut_test]
    test = exemples.loc[exemples["timestamp_dt"] >= debut_test]
    if (
        len(entrainement) < NB_EXEMPLES_MINIMUM
        or len(test) < NB_EXEMPLES_TEST_MINIMUM
        or entrainement["resultat"].nunique() < 2
        or test["resultat"].nunique() < 2
    ):
        print(
            "[OK] Entraînement ignoré : le split chronologique purgé ne contient pas "
            "assez d'exemples des deux classes dans les jeux d'entraînement et de test."
        )
        return

    evaluation = creer_modele()
    evaluation.fit(entrainement[FEATURES_MODELE], entrainement["resultat"])
    precision = accuracy_score(test["resultat"], evaluation.predict(test[FEATURES_MODELE]))
    precision_majoritaire = max(test["resultat"].mean(), 1 - test["resultat"].mean())

    modele = creer_modele()
    modele.fit(exemples[FEATURES_MODELE], exemples["resultat"])
    joblib.dump(modele, FICHIER_MODELE)
    print(
        f"[OK] Modèle entraîné sur {len(exemples)} exemple(s); "
        f"test chronologique purgé : {len(test)} exemple(s), "
        f"précision : {precision:.2%}, "
        f"référence classe majoritaire : {precision_majoritaire:.2%}."
    )


def creer_modele():
    """Construit une forêt aléatoire avec une complexité limitée."""
    return RandomForestClassifier(
        n_estimators=200,
        min_samples_leaf=3,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def _liquider_position(quantite, prix, capital_entree):
    prix_vente = prix * (1 - SLIPPAGE_ESTIME)
    capital = quantite * prix_vente * (1 - FRAIS_TAKER)
    return capital, capital / capital_entree - 1


def _appliquer_signal(signal, prix_execution, capital, quantite, capital_entree):
    if signal == "ACHAT" and quantite == 0:
        prix_achat = prix_execution * (1 + SLIPPAGE_ESTIME)
        capital_entree = capital
        quantite = capital / (prix_achat * (1 + FRAIS_TAKER))
        capital = 0.0
    elif signal == "VENTE" and quantite > 0:
        capital, rendement = _liquider_position(quantite, prix_execution, capital_entree)
        quantite = 0.0
        capital_entree = None
        return capital, quantite, capital_entree, rendement
    return capital, quantite, capital_entree, None


def simuler_backtest(donnees):
    """Simule une stratégie spot long-only avec exécution à la clôture suivante."""
    historique = donnees.sort_values("timestamp_dt").reset_index(drop=True)
    capital = 1.0
    prix_initial = float(historique.iloc[0]["prix_usd"])
    prix_final_marche = float(historique.iloc[-1]["prix_usd"])
    achat_conservation = (
        prix_final_marche * (1 - SLIPPAGE_ESTIME) * (1 - FRAIS_TAKER)
        / (prix_initial * (1 + SLIPPAGE_ESTIME) * (1 + FRAIS_TAKER))
        if len(historique) > 1
        else 1.0
    )
    quantite = 0.0
    capital_entree = None
    rendements_trades = []
    capital_apres_trades = [capital]

    for index in range(len(historique)):
        ligne = historique.loc[index]
        prix_courant = float(ligne["prix_usd"])
        valeur_liquidation = (
            quantite * prix_courant * (1 - SLIPPAGE_ESTIME) * (1 - FRAIS_TAKER)
            if quantite > 0
            else capital
        )
        capital_apres_trades.append(valeur_liquidation)
        if index == len(historique) - 1:
            break

        signal = historique.loc[index, "signal"]
        prochain = historique.loc[index + 1]
        if prochain["timestamp_dt"] - ligne["timestamp_dt"] != pd.Timedelta(hours=1):
            if quantite > 0:
                capital, rendement = _liquider_position(quantite, prix_courant, capital_entree)
                rendements_trades.append(rendement)
                capital_apres_trades[-1] = capital
                quantite = 0.0
                capital_entree = None
            continue
        prix_execution = float(prochain["prix_usd"])
        capital, quantite, capital_entree, rendement = _appliquer_signal(
            signal, prix_execution, capital, quantite, capital_entree
        )
        if rendement is not None:
            rendements_trades.append(rendement)
            capital_apres_trades.append(capital)

    if quantite > 0:
        capital, rendement = _liquider_position(
            quantite, float(historique.iloc[-1]["prix_usd"]), capital_entree
        )
        rendements_trades.append(rendement)
        capital_apres_trades[-1] = capital

    serie_capital = pd.Series(capital_apres_trades, dtype=float)
    drawdown = serie_capital / serie_capital.cummax() - 1
    taux_reussite = (
        sum(rendement > 0 for rendement in rendements_trades) / len(rendements_trades) * 100
        if rendements_trades
        else 0.0
    )
    return {
        "rendement_net_pct": (capital - 1) * 100,
        "drawdown_max_pct": abs(float(drawdown.min())) * 100,
        "nombre_trades": len(rendements_trades),
        "taux_reussite_pct": taux_reussite,
        "achat_conservation_pct": (achat_conservation - 1) * 100,
    }


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