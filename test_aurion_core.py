import unittest
import os
from unittest.mock import patch

import pandas as pd

import broker as broker_module
from aurion_price_fetcher import _bougies_cloturees
from aurion_signals import calculer_indicateurs, preparer_exemples, simuler_backtest
from broker import Broker


class FauxCurseur:
    def __init__(self, details):
        self.details = details
        self.requete = ""

    def execute(self, requete):
        self.requete = requete

    def fetchone(self):
        if "action = 'initialisation'" in self.requete:
            return ({"solde_initial_usdt": 5000.0},)
        return None

    def fetchall(self):
        return [(details,) for details in self.details]


class TestsAurionCore(unittest.TestCase):
    def test_un_label_ne_traverse_pas_un_trou_horaire(self):
        horodatages = pd.date_range("2026-01-01", periods=120, freq="h", tz="UTC")
        horodatages = horodatages.to_series().reset_index(drop=True)
        horodatages.loc[60:] += pd.Timedelta(hours=2)
        donnees = pd.DataFrame({
            "timestamp": horodatages.astype(str),
            "prix_usd": [100 + index * 0.1 for index in range(120)],
        })

        indicateurs = calculer_indicateurs(donnees)
        indicateurs.loc[55, "signal"] = "ACHAT"
        indicateurs.loc[90, "signal"] = "ACHAT"
        exemples = preparer_exemples(indicateurs)

        self.assertNotIn(55, exemples.index)
        self.assertIn(90, exemples.index)

    def test_backtest_inclut_les_couts_et_un_trade(self):
        donnees = pd.DataFrame({
            "timestamp_dt": pd.date_range("2026-01-01", periods=50, freq="h", tz="UTC"),
            "prix_usd": [100 + index for index in range(50)],
            "signal": [
                "ACHAT" if index == 30 else "VENTE" if index == 40 else "ATTENTE"
                for index in range(50)
            ],
        })

        resultat = simuler_backtest(donnees)

        self.assertEqual(resultat["nombre_trades"], 1)
        self.assertGreater(resultat["rendement_net_pct"], 0)
        self.assertLess(resultat["rendement_net_pct"], resultat["achat_conservation_pct"])

    def test_position_et_solde_sont_reconstruits_du_journal(self):
        curseur = FauxCurseur([
            {
                "sens": "achat",
                "quantite": 1.0,
                "prix_execution": 100.0,
                "frais_usdt": 0.1,
            },
            {
                "sens": "vente",
                "quantite": 0.5,
                "prix_execution": 120.0,
                "frais_usdt": 0.06,
            },
        ])

        solde_usdt, position_paxg = Broker._recuperer_etat_simule(curseur)

        self.assertAlmostEqual(position_paxg, 0.5)
        self.assertAlmostEqual(solde_usdt, 5000.0 - 100.1 + 59.94)

    def test_ordre_refuse_quantite_non_finie_avant_connexion(self):
        broker = object.__new__(Broker)

        with self.assertRaisesRegex(ValueError, "nombre fini"):
            broker.passer_ordre("achat", float("nan"))

    def test_bougie_non_cloturee_est_ignoree(self):
        maintenant_ms = pd.Timestamp.now(tz="UTC").timestamp() * 1000
        bougies = [[0] * 7 for _ in range(2)]
        bougies[0][6] = int(maintenant_ms - 60_000)
        bougies[1][6] = int(maintenant_ms + 3_600_000)

        self.assertEqual(_bougies_cloturees(bougies), [bougies[0]])

    def test_mode_reel_refuse_les_cles_absentes(self):
        environnement = {
            "BINANCE_API_KEY": "",
            "BINANCE_API_SECRET": "",
        }
        with patch.object(broker_module, "MODE_SIMULATION", False):
            with patch.dict(os.environ, environnement):
                with self.assertRaisesRegex(ValueError, "BINANCE_API_KEY"):
                    Broker()


if __name__ == "__main__":
    unittest.main(verbosity=2)