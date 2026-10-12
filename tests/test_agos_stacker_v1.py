"""Unit tests for independent bounded Stacker concept; no network dependencies."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import agos_stacker_v1_core as s

def bar(o=100,h=101,l=99,c=100,t=0):
    return dict(o=o,h=h,l=l,c=c,t=t,ct=t+3_600_000-1,day="2025-01-01")

class StackerTests(unittest.TestCase):
    def test_band_excludes_future(self):
        rows=[bar(c=100.) for _ in range(20)]+[bar(c=20.)]
        self.assertEqual(s.band(rows,19),(100.,100.))
        self.assertLess(s.band(rows,20)[0],100.)

    def test_grid_and_hard_stop(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"stacker")
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["stop"],90.5)
        self.assertEqual(p["levels"],[100,98,96,94])
        self.assertEqual(len(p["quantities"]),4)
        planned_loss=sum(q*(v-p["stop"]) for q,v in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(planned_loss,150+1e-8)
        max_notional=sum(q*v for q,v in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(max_notional,14000+1e-8)

    def test_short_stop_grid(self):
        p=s.entry_cycle("ETHUSDT","crypto","SHORT",100,2,0,20000,"stacker")
        self.assertAlmostEqual(p["stop"],109.5)
        self.assertEqual(p["levels"],[100,102,104,106])
        planned_loss=sum(q*(p["stop"]-v) for q,v in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(planned_loss,150+1e-8)

    def test_inbar_all_adds_then_hard_stop(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"stacker")
        closed=s.apply_bar(p,bar(o=100,h=105,l=90,c=91), "crypto",is_entry_bar=True)
        self.assertEqual(closed,(90.5,"STOP"))
        self.assertEqual(p["next_add"],4)
        self.assertEqual(len(p["fills"]),4)
        trade=s.close_cycle(p,90.5,3600000,"STOP")
        self.assertLess(trade["pnl"],0)
        self.assertLess(trade["pnl"],-125)

    def test_tp_not_available_on_add_candle(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"stacker")
        ret=s.apply_bar(p,bar(o=100,h=120,l=96,c=104),"crypto",is_entry_bar=True)
        self.assertIsNone(ret)
        self.assertEqual(len(p["fills"]),3)
        ret=s.apply_bar(p,bar(o=100,h=120,l=99,c=110,t=3600000),"crypto")
        self.assertEqual(ret[1],"TP")

    def test_stop_priority(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"single")
        self.assertEqual(s.apply_bar(p,bar(o=100,h=120,l=88,c=110),"crypto",True),
                         (90.5,"STOP"))

    def test_genuine_gap_stop(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"stacker")
        self.assertEqual(s.apply_bar(p,bar(o=85,h=95,l=80,c=90),"crypto"),
                         (85,"GAP_STOP"))
        self.assertEqual(len(p["fills"]),1)

    def test_mtm_includes_open_losses(self):
        curve=[dict(equity=20000),dict(equity=19500),dict(equity=20010)]
        m=s.metrics([],curve)
        self.assertAlmostEqual(m["max_mtm_drawdown_pct"],2.5)
        self.assertTrue(m["open_equity_included"])

    def test_risk_matched_single(self):
        p=s.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"single")
        self.assertEqual(len(p["quantities"]),1)
        self.assertLessEqual(p["quantities"][0]*(100-p["stop"]),150+1e-8)

if __name__=="__main__":
    unittest.main()
