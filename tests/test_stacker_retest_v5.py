"""Invariant tests: fresh-position retest, hard stops, lookahead, fee inclusive risk."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stacker_retest_v5_core as v5


def b(i, o=100.,h=101.,l=99.,c=100.):
    return {"t":i*3600000,"ct":(i+1)*3600000-1,
            "o":o,"h":h,"l":l,"c":c,"atr14":2.,"ema20":100.,
            "day":"2025-01-01","v":100.}


def pack():
    return {"hour":[b(i) for i in range(24)],
            "h4_closes":[],"h4":[]}


def signal(i=6):
    return {"side":"LONG","sign":1,"hour_index":i,
            "close":100.,"parent_tp_t":0,"signal_t":(i+1)*3600000-1}


def entry(mode="retest",opening=100.):
    p=pack(); p["hour"][6]=b(6)
    return v5.child_entry("BTCUSDT",b(7,o=opening),p["hour"][6],
                           signal(),20000.,.0006,mode,p)


class FreshRetestTests(unittest.TestCase):
    def test_is_a_new_independent_trade_with_2r(self):
        p=entry()
        self.assertIsNotNone(p)
        self.assertEqual(p["kind"],"child")
        self.assertAlmostEqual(p["stop"],98.5)
        self.assertAlmostEqual(p["tp"],103.0)
        self.assertLessEqual(p["qty"]*(1.5+.001*(100+98.5)),75.+1e-8)
        self.assertEqual(p["parent_tp_t"],0)

    def test_no_entry_if_open_gaps_too_far(self):
        self.assertIsNone(entry(opening=102.))

    def test_new_long_stop_never_moves_lower(self):
        p=entry()
        old=p["stop"]
        v5.process_child(p,b(7,o=100,h=102.5,l=99.5,c=102.),
                         "crypto",.0006,entry_bar=True)
        self.assertGreaterEqual(p["active_stop"],old)
        self.assertEqual(p["active_stop"],100.)

    def test_intrabar_stop_wins_over_two_r_target(self):
        p=entry()
        done=v5.process_child(p,b(7,o=100,h=106,l=98,c=105),
                              "crypto",.0006,entry_bar=True)
        self.assertEqual(done["reason"],"STOP")
        self.assertLess(done["pnl"],0.)

    def test_old_stop_applies_until_future_candle(self):
        p=entry()
        first=v5.process_child(p,b(7,o=100,h=103,l=99,c=102),
                               "crypto",.0006,entry_bar=True)
        self.assertIsNone(first)
        self.assertEqual(p["active_stop"],100)
        done=v5.process_child(p,b(8,o=101,h=102,l=99,c=101),
                              "crypto",.0006,entry_bar=False)
        self.assertEqual(done["reason"],"STOP")
        self.assertEqual(done["exit"],100)

    def test_gap_fills_real_open(self):
        p=entry()
        done=v5.process_child(p,b(8,o=95,h=96,l=94,c=95),
                              "crypto",.0006,entry_bar=False)
        self.assertEqual(done["reason"],"GAP_STOP")
        self.assertEqual(done["exit"],95)

    def test_no_signal_before_parent_tp(self):
        p=pack()
        p["hour"][21]=b(21,o=101.5,h=103.5,l=100.5,c=103.)
        p["hour"][21]["ema20"]=102
        watch={"tp":103,"atr":2,"sign":1,"side":"LONG",
               "tp_time":p["hour"][21]["ct"],"bars_remaining":48}
        self.assertIsNone(v5.test_retest_signal(p,21,watch,"retest"))

    def test_retest_requires_close_confirmed(self):
        p=pack()
        p["hour"][21]=b(21,o=101.5,h=103.5,l=100.5,c=103.)
        p["hour"][21]["ema20"]=102
        w={"tp":103,"atr":2,"sign":1,"side":"LONG",
           "tp_time":p["hour"][20]["ct"],"bars_remaining":48}
        sig=v5.test_retest_signal(p,21,w,"retest")
        self.assertIsNotNone(sig)
        self.assertEqual(sig["signal_t"],p["hour"][21]["ct"])
        p["hour"][21]["c"]=101
        self.assertIsNone(v5.test_retest_signal(p,21,w,"retest"))

    def test_htf_reentry_rejects_opposite_slope(self):
        p=pack()
        p["hour"][21]=b(21,o=101.5,h=103.5,l=100.5,c=103.)
        p["hour"][21]["ema20"]=102
        w={"tp":103,"atr":2,"sign":1,"side":"LONG",
           "tp_time":p["hour"][20]["ct"],"bars_remaining":48}
        with patch.object(v5.v4,"trend_reentry_ok",return_value=False):
            self.assertIsNone(v5.test_retest_signal(p,21,w,"retest_htf"))
        with patch.object(v5.v4,"trend_reentry_ok",return_value=True):
            self.assertIsNotNone(v5.test_retest_signal(p,21,w,"retest_htf"))

    def test_barrier_filter_needs_room_above_new_entry(self):
        p=pack()
        s=signal()
        st={"pivot_high":[102.],"pivot_low":[95.],"ema20":100.,"ema50":105}
        with patch.object(v5.v4,"confirmed_structure_before",return_value=st):
            self.assertIsNone(v5.child_entry("BTCUSDT",b(7),p["hour"][6],s,20000.,.0006,
                                              "retest_htf_barrier",p))
        st["pivot_high"]=[108.]
        with patch.object(v5.v4,"confirmed_structure_before",return_value=st):
            self.assertIsNotNone(v5.child_entry("BTCUSDT",b(7),p["hour"][6],s,20000.,.0006,
                                                 "retest_htf_barrier",p))

    def test_fee_stress_decreases_net_pnl(self):
        p=entry()
        a=v5.close_child(p,103,36000000,"TP_2R",.0006)
        b=v5.close_child(p,103,36000000,"TP_2R",.0010)
        self.assertLess(b["pnl"],a["pnl"])

    def test_no_double_counting_marked_open_position(self):
        p=entry()
        expected=p["sign"]*p["qty"]*(101-p["entry"])-p["fees"]
        self.assertAlmostEqual(v5.floating(p,101),expected)

if __name__=="__main__": unittest.main()
