# Aurion - Bot de Trading Or Tokenisé

Bot personnel qui suit le prix de l'or tokenisé (PAXG/USDT) via l'API publique de Binance.

## Fonctionnalités

- Récupération automatique du prix PAXG/USDT toutes les 15 minutes via GitHub Actions
- Stockage des données dans une base Supabase (Postgres)
- Historique initial bootstrap pour le backtesting
- Gestion des erreurs réseau avec retry automatique

## Structure du projet

```
aurion/
├── .github/workflows/fetch_price.yml  # Workflow GitHub Actions
├── aurion_price_fetcher.py            # Script principal
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

## Initialisation de la base

Exécutez le script en mode complet pour créer la table et peupler l'historique :

```bash
python aurion_price_fetcher.py
```

Cela va :
- Créer la table `prix` dans Supabase
- Récupérer 500 bougies historiques (1h)
- Insérer le prix actuel

## Déploiement sur GitHub Actions

1. **Créer un repository GitHub** et pousser le code
2. **Ajouter le secret `DATABASE_URL`** dans GitHub Settings > Secrets and variables > Actions
3. **Le workflow s'exécute automatiquement** toutes les 15 minutes

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

## Structure de la base de données

Table `prix` :
- `id` (SERIAL PRIMARY KEY)
- `timestamp` (TEXT NOT NULL) - ISO format UTC
- `prix_usd` (REAL NOT NULL)
- `source` (TEXT NOT NULL) - "live" ou "historique_1h"

## Coûts

- **GitHub Actions** : Gratuit (2000 minutes/mois)
- **Supabase** : Free tier (500 MB de stockage, 2 connexions simultanées)

## Développement

Le script est en Python minimaliste avec :
- `psycopg2-binary` pour la connexion Postgres
- `requests` pour l'API Binance
- `python-dotenv` pour la gestion des variables d'environnement

## Notes de sécurité

- **Jamais** de clés API Binance nécessaires (endpoints publics)
- **DATABASE_URL** est stocké dans les secrets GitHub, jamais dans le code
- Le fichier `.env` est ignoré par Git (voir `.gitignore`)
