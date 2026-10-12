"""Entry v9 adversarial tests: resting order causality and loss caps."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import entry_execution_v9_core as v9
import entry_first_v8_core as v8


def bar(i,o=100.,h=101.,l=99.,c=100.):
    t=i*3600000
    return dict(t=t,ct=t+3599999,o=o,h=h,l=l,c=c,atr14=2.,
                day="2025-01-01",v=100)


def signal():
    return dict(side="LONG",sign=1,anchor=97.,entry_atr=2.,
                source_close=100.,signal_t=3_599_999,
                kind="sweep",structure_level=99.)


def sorder(mode="limit_half"):
    x,reason=v9.make_order("BTCUSDT",mode,signal(),bar(1),1,20000.,.0006)
    assert x is not None, reason
    return x


class ExecutionV9(unittest.TestCase):
    def test_eight_predeclared_modes(self):
        self.assertEqual(len(v9.MODES),8)
        self.assertEqual(len(set(v9.MODES)),8)

    def test_limit_levels_are_causal_and_improve_entry(self):
        self.assertAlmostEqual(v9.proposed_limit("limit_half",signal()),99.)
        self.assertAlmostEqual(v9.proposed_limit("limit_reclaim",signal()),99.2)
        self.assertAlmostEqual(v9.proposed_limit("limit_deep",signal()),98.4)
        for mode in ("limit_half","limit_reclaim","limit_deep"):
            self.assertLess(v9.proposed_limit(mode,signal()),100.)

    def test_unfavorable_limit_does_not_place(self):
        s=signal();s["structure_level"]=101
        self.assertIsNone(v9.proposed_limit("limit_reclaim",s))

    def test_limit_stop_and_fee_inclusive_planned_risk(self):
        order=sorder()
        self.assertAlmostEqual(order["stop"],96.6)
        px=order["limit"]
        risk=px-order["stop"]
        worst=order["qty"]*(risk+.001*(px+order["stop"]))
        self.assertLessEqual(worst,100.000001)
        self.assertLessEqual(order["qty"]*px,14000.001)

    def test_limit_resting_fill_is_at_order_price(self):
        x=sorder()
        price,why=v9.fill_price(x,bar(1,100,101,98,100))
        self.assertEqual(why,"resting_limit")
        self.assertEqual(price,99.)

    def test_good_open_below_limit_improves_fill(self):
        x=sorder()
        px,reason=v9.fill_price(x,bar(1,98.5,100,98,99))
        self.assertEqual(reason,"open_improved")
        self.assertEqual(px,98.5)
        pos=v9.activate(x,bar(1,98.5,100,98,99),px,.0006)
        self.assertAlmostEqual(pos["target"],98.5+2*(98.5-96.6))
        self.assertLess(pos["risk_price"],99-96.6)

    def test_gap_through_stop_cancels_without_trade(self):
        px,why=v9.fill_price(sorder(),bar(1,95,100,94,100))
        self.assertIsNone(px)
        self.assertEqual(why,"open_through_stop")

    def test_ambiguous_limit_touch_and_stop_is_stopped(self):
        x=sorder()
        b=bar(1,100,108,96.2,104)
        price,why=v9.fill_price(x,b)
        self.assertEqual(why,"resting_limit")
        p=v9.activate(x,b,price,.0006)
        tr=v8.update_position(p,b,"crypto",.0006,entry_bar=True)
        self.assertEqual(tr["reason"],"STOP")
        self.assertLess(tr["pnl"],0)
        self.assertEqual(tr["mfe_r"],0)

    def test_no_entry_candle_take_profit(self):
        x=sorder()
        b=bar(1,100,110,98.8,105)
        px,_=v9.fill_price(x,b)
        p=v9.activate(x,b,px,.0006)
        self.assertIsNone(v8.update_position(p,b,"crypto",.0006,entry_bar=True))

    def test_short_side_limit_and_stop(self):
        s=signal()
        s.update(side="SHORT",sign=-1,source_close=100,anchor=103,
                 structure_level=101)
        x,why=v9.make_order("ETHUSDT","limit_half",s,bar(1),1,20000,.0006)
        self.assertIsNotNone(x,why)
        self.assertEqual(x["limit"],101.)
        p,why=v9.fill_price(x,bar(1,100,102,99,100))
        self.assertEqual((p,why),(101.,"resting_limit"))
        tr=v8.update_position(v9.activate(x,bar(1,100,104,99,100),101.,.0006),
                               bar(1,100,104,99,100),"crypto",.0006,entry_bar=True)
        self.assertEqual(tr["reason"],"STOP")

    def test_signal_h4_timestamp_strict(self):
        p={"h4":[{"ct":3599999,"h":120,"l":100,"atr14":5.},
                 {"ct":7199999,"h":105,"l":100,"atr14":5.}],
           "h4_closes":[3599999,7199999]}
        s=signal()
        self.assertFalse(v9.shock_accept(p,s))
        s["signal_t"]=7199999
        self.assertTrue(v9.shock_accept(p,s))
        s["signal_t"]=6199999
        self.assertFalse(v9.shock_accept(p,s))

    def test_two_hour_expiry_does_not_fill_third_hour(self):
        bars=[bar(0),bar(1),bar(2),bar(3)]
        # An order starts at t=hour1. A limit at 99 gets no touch
        # in hour1,2 but touches in hour3: expired before hour3.
        bars[1].update(o=100,h=103,l=99.5,c=101.)
        bars[2].update(o=101,h=102,l=99.3,c=100.)
        bars[3].update(o=100,h=101,l=98,c=99.)
        packs={"BTCUSDT":{"hour":bars,"h4":[]}}
        pre={"BTCUSDT":{bars[1]["t"]:signal()}}
        result=v9.simulate(packs,"crypto","limit_half_2h",0,4*3600000,
                           trade_symbols=["BTCUSDT"],precomputed=pre)
        self.assertEqual(result["metrics"]["trade_count"],0)
        self.assertEqual(result["metrics"]["filled_orders"],0)
        self.assertEqual(result["metrics"]["submitted_orders"],1)
        self.assertEqual(result["metrics"]["cancels"]["expired"],1)

    def test_market_baseline_same_as_v8_on_synthetic_market(self):
        bars=[bar(i) for i in range(7)]
        bars[1].update(o=100,h=100.5,l=99.0,c=100.)
        bars[2].update(o=100,h=101,l=98.8,c=99.5)
        bars[3].update(o=99.5,h=107,l=99,c=105)
        pack={"hour":bars,"h4":[]}
        allm={k:{} for k in v8.MODES}
        allm["sweep"]={bars[1]["t"]:signal()}
        ref=v8.simulate({"BTCUSDT":pack},"crypto","sweep",0,7*3600000,
                        trade_symbols=["BTCUSDT"],
                        precomputed={"BTCUSDT":allm})
        actual=v9.simulate({"BTCUSDT":pack},"crypto","market",0,7*3600000,
                           trade_symbols=["BTCUSDT"],
                           precomputed={"BTCUSDT":allm["sweep"]})
        self.assertEqual(ref["metrics"]["trade_count"],actual["metrics"]["trade_count"])
        self.assertAlmostEqual(ref["metrics"]["return_pct"],actual["metrics"]["return_pct"])
        self.assertAlmostEqual(ref["metrics"]["max_mtm_dd_pct"],
                               actual["metrics"]["max_mtm_dd_pct"])

if __name__=="__main__":unittest.main()
