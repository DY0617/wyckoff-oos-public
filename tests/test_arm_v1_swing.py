"""Offline invariants for ARM v1. Run: python -m unittest discover -s tests -p test_arm_v1_swing.py"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import arm_v1_swing_core as arm

UTC = timezone.utc


def position():
    return dict(sign=1, entry=100., stop=90., active_stop=90., risk=10.,
                tp1=120., tp2=135., remaining=1., stage=0,
                entry_index=0, entry_t=0, r=-arm.COST*100/10, legs=[])


def candle(o=100, h=110, l=95, c=105, ct=3_600_000):
    return dict(o=o, h=h, l=l, c=c, ct=ct, t=ct-3_600_000, day="2025-01-01")


class TestARM(unittest.TestCase):
    def test_ema_bootstrap(self):
        bars = [dict(o=100.,h=100.,l=100.,c=100.,v=1.,t=i,ct=i+1,day=str(i))
                for i in range(210)]
        arm.indicators(bars)
        self.assertIsNone(bars[49]["ema50"])
        self.assertAlmostEqual(bars[209]["ema200"],100)
        self.assertAlmostEqual(bars[209]["ret60"],0)

    def test_stop_precedes_target_on_same_candle(self):
        p = position()
        self.assertTrue(arm.update_position(p,candle(h=150,l=80),1,"crypto"))
        self.assertEqual([x["reason"] for x in p["legs"]],["STOP"])
        self.assertLess(p["r"],-1.)

    def test_gap_stop_uses_actual_open(self):
        p = position()
        self.assertTrue(arm.update_position(p,candle(o=80,h=110,l=75,c=90),1,"crypto"))
        self.assertEqual(p["legs"][0]["exit_px"],80)
        self.assertLess(p["r"],-2.)

    def test_pre_entry_gap_is_not_charged_as_post_entry_gap(self):
        p = position()
        # The order is triggered above 100 later inside this candle.
        # Opening at 80 was BEFORE entry, so cannot be the stop exit.
        self.assertTrue(arm.update_position(p, candle(o=80,h=105,l=78,c=100),1,"crypto",entry_bar=True))
        self.assertEqual(p["legs"][0]["reason"],"STOP")
        self.assertEqual(p["legs"][0]["exit_px"],90)
        self.assertGreater(p["r"],-1.5)

    def test_breakeven_activates_only_after_tp1_candle(self):
        p = position()
        self.assertFalse(arm.update_position(p,candle(o=105,h=121,l=95,c=120),1,"crypto"))
        self.assertEqual(p["stage"],1)
        self.assertAlmostEqual(p["remaining"],0.5)
        self.assertEqual(p["active_stop"],100.)
        self.assertTrue(arm.update_position(p,candle(o=102,h=115,l=99,c=101),2,"crypto"))
        self.assertEqual([x["reason"] for x in p["legs"]],["TP1","STOP"])
        self.assertGreater(p["r"],0.9)

    def test_daily_is_strictly_prior_day(self):
        day0 = datetime(2025,1,1,tzinfo=UTC)
        data = []
        for i in range(220):
            d = day0 + timedelta(days=i)
            data.append(dict(t=int(d.timestamp()*1000),ct=int((d+timedelta(days=1)).timestamp()*1000)-1,
                             day=d.date().isoformat(),o=100+i,h=102+i,l=99+i,
                             c=101+i,v=1,session_hour=0))
        pack = arm.prepare(data,"stock")
        key = (day0+timedelta(days=200)).date().isoformat()
        self.assertEqual(arm.prev_daily(pack,key)["day"],data[199]["day"])
        self.assertEqual(arm.prev_daily(pack,data[0]["day"]),None)

    def test_no_incomplete_stock_4h_candle(self):
        bars = [dict(t=i*3_600_000,ct=(i+1)*3_600_000-1,day="2025-01-01",
                     session_hour=i,o=100.,h=100.,l=100.,c=100.,v=1.)
                for i in range(7)]
        p = arm.prepare(bars,"stock")
        self.assertEqual(len(p["h4"]),2)
        self.assertIsNone(arm.confirmed_h4(p,2*3_600_000))
        self.assertEqual(arm.confirmed_h4(p,4*3_600_000)["count"],4)

    def test_funding_long_short_sign(self):
        tr = dict(market="crypto",symbol="BTCUSDT",entry=100.,risk=10.,r=0.,
                  entry_t=0, sign=1,legs=[dict(fraction=1.,exit_t=1000)])
        arm.apply_funding([tr],{"BTCUSDT":[(500,0.001)]})
        self.assertAlmostEqual(tr["funding_r"],-0.01)
        tr["sign"] = -1
        arm.apply_funding([tr],{"BTCUSDT":[(500,0.001)]})
        self.assertAlmostEqual(tr["funding_r"],0.01)

    def test_portfolio_risk_cap(self):
        ts = [dict(entry_t=10,exit_t=100,symbol=f"S{i}",net_r=1) for i in range(5)]
        chosen, p = arm.portfolio(ts)
        self.assertEqual(len(chosen),3)
        self.assertAlmostEqual(p["return_pct"],1.5)


if __name__ == "__main__":
    unittest.main()
