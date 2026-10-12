"""Offline, reproducible Chaser v1 invariants; no network needed."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import chaser_v1_core as c


def bar(o=100,h=101,l=99,cl=100,t=0):
    return {"o":o,"h":h,"l":l,"c":cl,"t":t,
            "ct":t+3600000-1,"v":100,"atr14":2.0,"day":"2025-01-01"}


def sig(side="LONG",cl=100,atr=2):
    return {"symbol":None,"side":side,"sign":1 if side=="LONG" else -1,
            "signal_t":-1,"signal_close":cl,"atr":atr}


class ChaserTests(unittest.TestCase):
    def test_entry_risk_and_size(self):
        p=c.open_position("BTCUSDT",bar(),sig(),20000,"crypto",0.0006)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["stop"],96)
        self.assertLessEqual(p["actual_planned_risk"],100.01)
        self.assertLessEqual(p["initial_qty"]*p["entry"],15000.01)
        self.assertAlmostEqual(p["tp1"],106)
        self.assertAlmostEqual(p["tp2"],112)

    def test_unfavorable_gap_reject(self):
        self.assertIsNone(c.open_position("BTCUSDT",bar(o=104),sig(),20000,"crypto",0.0006))
        self.assertIsNotNone(c.open_position("BTCUSDT",bar(o=99),sig(),20000,"crypto",0.0006))

    def test_stop_first_on_same_candle(self):
        p=c.open_position("BTCUSDT",bar(),sig(),20000,"crypto",0.0006)
        _,done=c.process_candle(p,bar(h=120,l=95), "crypto",0.0006,True)
        self.assertTrue(done)
        self.assertEqual([x["reason"] for x in p["legs"]],["STOP"])
        self.assertLess(p["net_pnl"],0)

    def test_open_gap_stop_is_at_open(self):
        p=c.open_position("BTCUSDT",bar(),sig(),20000,"crypto",0.0006)
        _,done=c.process_candle(p,bar(o=90,h=100,l=88), "crypto",0.0006,False)
        self.assertTrue(done)
        self.assertEqual(p["legs"][0]["px"],90)

    def test_next_bar_breakeven(self):
        p=c.open_position("BTCUSDT",bar(),sig(),20000,"crypto",0.0006)
        _,done=c.process_candle(p,bar(h=108,l=98,cl=107),"crypto",0.0006,True)
        self.assertFalse(done)
        self.assertAlmostEqual(p["remaining_qty"],p["initial_qty"]*0.5)
        self.assertEqual(p["active_stop"],100)
        _,done=c.process_candle(p,bar(o=104,h=106,l=99,cl=103,t=3600000),"crypto",0.0006,False)
        self.assertTrue(done)
        self.assertEqual([x["reason"] for x in p["legs"]],["TP1","STOP"])

    def test_compression_uses_prior_bars_only(self):
        history=[bar(o=100,h=101,l=99,cl=100) for _ in range(20)]
        current=bar(o=100,h=104,l=99,cl=104)
        history.append(current)
        self.assertFalse(c.compression_filter(history,20,"LONG",2))  # range 5 < 1 ATR requirement? 5>=2: yes, body4/range5 yes, volume100<120
        history[-1]["v"]=150
        self.assertTrue(c.compression_filter(history,20,"LONG",2))

    def test_true_ohlc_crypto_short(self):
        p=c.open_position("ETHUSDT",bar(),sig("SHORT"),20000,"crypto",0.0006)
        self.assertAlmostEqual(p["stop"],104)
        self.assertAlmostEqual(p["tp1"],94)
        _,done=c.process_candle(p,bar(o=100,h=105,l=90,cl=93),"crypto",0.0006,True)
        self.assertTrue(done)
        self.assertEqual(p["legs"][-1]["reason"],"STOP")

    def test_three_concurrent_positions_cap_before_future_candle(self):
        syms=["AAA","BBB","CCC","DDD"]
        packs={"SPY":{"hour":[]}}
        packs.update({s:{"hour":[bar(t=0),bar(t=3600000)]} for s in syms})
        with patch.object(c,"build_signals",side_effect=lambda pack,bench,market,v,st,en:{0:sig()}):
            rep=c.simulate(packs,"stock","breakout",0,7200000,0.0006)
        self.assertEqual(rep["metrics"]["trades"],3)
        self.assertLessEqual(max(x["open_count"] for x in rep["curve"]),3)

    def test_fee_stress_cannot_improve_flat_trade(self):
        a=c.open_position("AAA",bar(),sig(),20000,"stock",0.0006)
        b=c.open_position("AAA",bar(),sig(),20000,"stock",0.0010)
        da=c.settle_leg(a,a["remaining_qty"],100,3600000,"END",0.0006)
        db=c.settle_leg(b,b["remaining_qty"],100,3600000,"END",0.0010)
        self.assertLess(b["net_pnl"],a["net_pnl"])
        self.assertLess(db,da)


if __name__=="__main__":
    unittest.main()
