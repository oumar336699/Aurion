# Aurion - Suivi et expérimentation PAXG/USDT

Aurion collecte les clôtures horaires de PAXG/USDT, produit des signaux techniques et permet de les évaluer hors échantillon. Le broker est une brique séparée, en simulation par défaut. Aurion ne promet pas de rentabilité et n'envoie aucun ordre réel par défaut.

## Fonctionnalités

- Récupération automatique des clôtures horaires PAXG/USDT via l'API publique Binance
- Stockage des données dans une base Supabase (Postgres)
- Historique initial de 5 000 clôtures horaires pour l'entraînement et le backtesting
- Gestion des erreurs réseau avec retry automatique
- Signaux basés sur croisements de moyennes et RSI, avec volatilité et confiance ML
- Backtest spot long-only avec frais, slippage estimé, drawdown et références
- Broker Binance indépendant, limité au paper trading par défaut

## Structure du projet

```
aurion/
├── .github/workflows/fetch_price.yml  # Workflow GitHub Actions
├── aurion_price_fetcher.py            # Script principal
├── aurion_signals.py                   # Indicateurs, entraînement et backtest
├── broker.py                           # Interface broker, simulation par défaut
├── test_aurion_core.py                 # Tests locaux sans réseau ni Supabase
├── requirements.txt                    # Dépendances Python
├── .env.example                        # Exemple de configuration
├── .gitignore                          # Fichiers ignorés par Git
├── test_connection.py                  # Script de test de connexion
└── README.md                           # Ce fichier
```

## Configuration locale

1. **Créer un compte Supabase gratuit** (si ce n'est pas déjà fait)
2. **Récupérer la connexion Postgres** depuis Supabase Dashboard > Settings > Database
3. **Créer le fichier `.env`** à partir de `.env.example` :

```bash
cp .env.example .env
```

4. **Configurer `DATABASE_URL`** dans `.env` :

```
DATABASE_URL=postgresql://postgres:[MOT_DE_PASSE]@[HOST]:[PORT]/postgres
```

5. **Installer les dépendances** :

```bash
pip install -r requirements.txt
```

6. **Tester la connexion** :

```bash
python test_connection.py
```

## Collecte des données

Exécutez le script en mode complet pour créer la table et peupler l'historique :

```bash
python aurion_price_fetcher.py
```

Cela va :
- Créer la table `prix` dans Supabase
- Récupérer 5 000 bougies Binance 1h clôturées (requêtes paginées de 1 000 bougies)
- Éviter les doublons grâce à un index unique sur l'horodatage

Les anciennes lignes CoinGecko ne sont pas utilisées pour les indicateurs. Le script de migration déduplique les horodatages existants avant de créer l'index unique.

## Déploiement sur GitHub Actions

1. **Créer un repository GitHub** et pousser le code
2. **Ajouter le secret `DATABASE_URL`** dans GitHub Settings > Secrets and variables > Actions
3. **Le workflow collecte une clôture horaire** à la minute 5 (UTC)

Vous pouvez aussi déclencher manuellement le workflow depuis l'onglet "Actions" sur GitHub.

## Utilisation

### Mode complet (local uniquement)
```bash
python aurion_price_fetcher.py
```

### Mode fetch_only (GitHub Actions)
```bash
python aurion_price_fetcher.py fetch_only
```

### Signaux et backtest
```bash
python aurion_signals.py backtest
python aurion_signals.py entrainer
python aurion_signals.py fetch_only
```

Le modèle est entraîné seulement si l'historique contient au moins 50 exemples utilisables et si le split chronologique purgé contient assez d'exemples des deux classes. Le backtest estime la confiance en walk-forward mensuel, sans utiliser les résultats futurs. Il suppose une exécution à la clôture horaire suivante et applique les frais/slippage configurés; il compare le rendement à l'achat-conservation et à l'absence de trade. Ces hypothèses restent une approximation: la précision de classification n'est pas une mesure de rentabilité, et les performances passées ne préjugent pas des performances futures. Le mode `backtest` remplace le contenu de la table `signaux`.

Les tests locaux sans connexion à la base se lancent ainsi:

```bash
python -m unittest discover -s . -p "test_aurion_core.py" -v
```

### Broker en simulation
`broker.py` n'est pas branché au pipeline et n'exécute aucun ordre réel tant que `MODE_SIMULATION = True`. Dans ce mode, les ordres sont valorisés à partir de la dernière clôture Binance connue, avec un solde initial, des frais et un slippage configurables; ils sont inscrits dans `ordres_simules`.

```python
from broker import Broker

broker = Broker()
print(broker.get_solde())
print(broker.passer_ordre("achat", 0.001))
print(broker.get_position())
```

Le broker refuse les achats dépassant le solde simulé et les ventes dépassant la position. En mode réel, il exige les clés Binance et limite le notionnel à `AURION_LIMITE_ORDRE_USDT` par ordre. Ne passe pas `MODE_SIMULATION` à `False` avant d'avoir testé le paper trading, la base et les contrôles de risque.

## Structure de la base de données

Table `prix` :
- `id` (SERIAL PRIMARY KEY)
- `timestamp` (TEXT NOT NULL, unique) - ouverture de la bougie, ISO UTC
- `prix_usd` (REAL NOT NULL)
- `source` (TEXT NOT NULL) - `binance_1h`

Table `signaux` : indicateurs et confiance du modèle, avec un seul signal par horodatage.

Table `ordres_simules` : journal des consultations et ordres simulés, incluant le prix de référence, le prix d'exécution et les frais estimés.

## Coûts

- **GitHub Actions** : Gratuit (2000 minutes/mois)
- **Supabase** : Free tier (500 MB de stockage, 2 connexions simultanées)

## Développement

Le script est en Python minimaliste avec :
- `psycopg2-binary` pour la connexion Postgres
- `requests` pour l'API Binance
- `python-dotenv` pour la gestion des variables d'environnement
- `pandas`, `scikit-learn` et `joblib` pour les indicateurs et l'apprentissage
- `ccxt` pour l'interface Binance du broker

## Notes de sécurité

- La collecte publique et le mode simulation ne nécessitent aucune clé Binance
- Les clés API sont réservées au mode réel; désactive les permissions de retrait côté Binance
- **DATABASE_URL** est stocké dans les secrets GitHub, jamais dans le code
- Le fichier `.env` est ignoré par Git (voir `.gitignore`)
