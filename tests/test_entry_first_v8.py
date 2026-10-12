"""Pure unit tests: causal pivot recognition, next-open entries and MAE/MFE.

No network; protects against optimistic candle or future-data assumptions.
"""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import entry_first_v8_core as v8


def candle(i,o=100,h=101,l=99,c=100,atr=2):
    t=i*3600000
    return {"t":t,"ct":t+3600000-1,
            "o":o,"h":h,"l":l,"c":c,"atr14":atr,
            "day":"2025-01-01","v":100}


def fake_signal():
    return {"side":"LONG","sign":1,"anchor":98.5,
        "entry_atr":2,"source_close":100.,"signal_t":1,
        "kind":"choch","structure_level":105.}


def entry():
    p,reason=v8.open_trade("BTCUSDT","choch",fake_signal(),candle(8),20000.,.0006)
    assert p is not None
    return p


class EntryFirstV8Tests(unittest.TestCase):
    def test_five_frozen_signal_families(self):
        self.assertEqual(len(v8.MODES),5)
        self.assertEqual(len(set(v8.MODES)),5)

    def test_pivot_needs_two_completed_right_bars(self):
        bars=[candle(i) for i in range(9)]
        bars[4]["h"]=105
        h,low=v8.confirmed_pivots(bars)
        self.assertIsNone(h[5])
        self.assertEqual(h[6],105)
        self.assertEqual(h[8],105)

    def test_sweep_uses_pivot_confirmed_before_signal(self):
        hh=[candle(i,o=100,h=102,l=99,c=100) for i in range(27)]
        hh[21]["l"]=90
        hh[25].update(o=91,h=93,l=89,c=92)
        signals=v8.h4_sweeps({"h4":hh},"stock")
        self.assertTrue(any(x["t"]==hh[25]["ct"] and x["side"]=="LONG"
                            and x["extreme"]==89 for x in signals))
        hh[25]["c"]=89
        self.assertFalse(any(x["t"]==hh[25]["ct"] for x in
                             v8.h4_sweeps({"h4":hh},"stock")))

    def test_choch_must_break_prior_confirmed_pivot_next_open(self):
        bars=[candle(i) for i in range(38)]
        bars[10]["h"]=105
        bars[27].update(o=100,h=107,l=99,c=106)
        bars[29].update(o=105.7,h=108,l=104.9,c=107)
        cache=v8.precompute_signals({"hour":bars,"h4":[]},"stock")
        self.assertIn(bars[28]["t"],cache["choch"])
        self.assertNotIn(bars[27]["t"],cache["choch"])
        self.assertIn(bars[30]["t"],cache["breakout_retest"])

    def test_retest_cannot_be_the_breakout_candle(self):
        bars=[candle(i) for i in range(38)]
        bars[10]["h"]=105
        bars[27].update(o=100,h=107,l=99,c=106)
        cache=v8.precompute_signals({"hour":bars,"h4":[]},"stock")
        self.assertNotIn(bars[28]["t"],cache["breakout_retest"])

    def test_entry_has_fixed_two_r_and_risk_cap(self):
        p=entry()
        self.assertAlmostEqual(p["stop"],98.1)
        self.assertAlmostEqual(p["target"],103.8)
        gross=p["qty"]*p["risk_price"]
        stressed=p["qty"]*(p["risk_price"]+.001*(p["entry"]+p["stop"]))
        self.assertLessEqual(stressed,100.00001)
        self.assertLessEqual(p["qty"]*p["entry"],14000.01)
        self.assertLess(gross,100.)

    def test_excess_chase_rejects_entry(self):
        p,why=v8.open_trade("BTCUSDT","choch",fake_signal(),
                             candle(8,o=102),20000,.0006)
        self.assertIsNone(p)
        self.assertEqual(why,"too_late")

    def test_stop_first_no_favorable_wick_on_stop_bar(self):
        p=entry()
        done=v8.update_position(p,candle(8,o=100,h=120,l=97,c=110),
                                "crypto",.0006,entry_bar=True)
        self.assertEqual(done["reason"],"STOP")
        self.assertAlmostEqual(done["mae_r"],1.)
        self.assertEqual(done["mfe_r"],0.)
        self.assertLess(done["pnl"],0)

    def test_no_entry_candle_tp(self):
        p=entry()
        done=v8.update_position(p,candle(8,o=100,h=105,l=99.5,c=104),
                                "crypto",.0006,entry_bar=True)
        self.assertIsNone(done)
        done=v8.update_position(p,candle(9,o=103,h=105,l=101,c=104),
                                "crypto",.0006)
        self.assertEqual(done["reason"],"TP_2R")
        self.assertAlmostEqual(done["exit"],103.8)

    def test_existing_stop_gap_executes_at_open(self):
        p=entry()
        done=v8.update_position(p,candle(9,o=95,h=99,l=90,c=98),
                                "crypto",.0006)
        self.assertEqual(done["reason"],"GAP_STOP")
        self.assertEqual(done["exit"],95.)
        self.assertGreater(done["mae_r"],1.0)

    def test_short_uses_symmetric_stop_target(self):
        sw={"side":"SHORT","sign":-1,"anchor":101.5,
            "entry_atr":2.,"source_close":100.,"signal_t":1,
            "kind":"choch","structure_level":95.}
        p,reason=v8.open_trade("ETHUSDT","choch",sw,candle(8),20000,.0006)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["stop"],101.9)
        self.assertAlmostEqual(p["target"],96.2)

    def test_no_trade_portfolio_is_flat_and_not_nan(self):
        packs={"BTCUSDT":{"hour":[candle(0)],"h4":[]}}
        r=v8.simulate(packs,"crypto","sweep",0,4_000_000,
                     precomputed={"BTCUSDT":{x:{} for x in v8.MODES}},
                     trade_symbols=["BTCUSDT"])
        self.assertEqual(r["metrics"]["trade_count"],0)
        self.assertEqual(r["metrics"]["return_pct"],0)
        self.assertEqual(r["metrics"]["max_mtm_dd_pct"],0)

    def test_disjoint_mode_records(self):
        h=[candle(i) for i in range(38)]
        h[10]["h"]=105
        h[27].update(o=100,h=107,l=99,c=106)
        h[29].update(o=105,h=108,l=104.9,c=107)
        cache=v8.precompute_signals({"hour":h,"h4":[]},"stock")
        self.assertFalse(cache["sweep"])
        self.assertFalse(cache["sweep_choch"])
        self.assertTrue(cache["choch"])
        self.assertTrue(cache["breakout_retest"])

if __name__=="__main__":
    unittest.main()
