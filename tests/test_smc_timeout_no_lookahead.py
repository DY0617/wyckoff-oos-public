"""Regression tests: time exits must not use candles that start at/after expiry.

Run from repository root:
    python -m unittest discover -s tests -p "test_smc_timeout_no_lookahead.py"
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backtest_smc_liq_fvg_v01 as smc
import backtest_smc_liq_fvg_v04_htf_plateau as plateau
import backtest_easychart_synthesis_v01 as synthesis

BAR = 15 * 60 * 1000
HOUR = 60 * 60 * 1000


def fixture():
    bars = []
    for i in range(5):
        bars.append({
            "t": i * BAR,
            "o": 100.0,
            "h": 101.0 if i < 4 else 145.0,
            "l": 99.0,
            "c": 100.0 if i < 4 else 140.0,
            "v": 1.0,
        })
    return bars


def setup():
    return {
        "direction": "LONG",
        "entry": 100.0,
        "stop": 90.0,
        "risk": 10.0,
        "signal_t": -1,
        "sweep_i": 0,
        "disp_i": 0,
        "ob_overlap": False,
    }


class TestSMCTimeoutNoLookahead(unittest.TestCase):
    def assert_time_exit(self, trade):
        self.assertAlmostEqual(trade["r"], 0.0, places=8)
        self.assertEqual(trade["exit_t"], HOUR)

    def test_original_smc_engine(self):
        cfg = {
            "max_hold_hours": 1,
            "signal_minutes": 60,
            "cost_bps_per_side": 0,
            "tp_r": 2.0,
        }
        t = smc.simulate_trade(fixture(), [{"t": 0}], 0, setup(), cfg, "fixed2r")
        self.assertEqual(t["reason"], "TIME_EXIT")
        self.assert_time_exit(t)

    def test_htf_plateau_resimulation(self):
        t = dict(setup(), entry_t=0, symbol="TEST")
        out = plateau.resim(fixture(), t, target_r=2.0, max_hold=1, cost_bps=0)
        self.assertEqual(out["reason_v04"], "TIME")
        self.assert_time_exit(out)

    def test_easychart_synthesis_resimulation(self):
        t = dict(setup(), entry_t=0, symbol="TEST")
        out = synthesis.resim(fixture(), t, target_r=2.0, cost_bps=0, max_hold=1)
        self.assertEqual(out["reason_synth"], "TIME")
        self.assert_time_exit(out)


if __name__ == "__main__":
    unittest.main()
