"""V14 independent causality, risk budget, and v12 backward-compatibility tests."""
import sys,unittest
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import tactical_allocation_v12_core as old
import tactical_v14_core as new


def make_packs(slope_b=.002,slope_eth=.003):
    names=("BTCUSDT","ETHUSDT","SOLUSDT")
    packs={}
    begin=date(2023,1,1)
    for sym,slope in zip(names,(slope_b,slope_eth,.001)):
        arr=[]
        for i in range(760):
            day=(begin+timedelta(days=i)).isoformat()
            c=120*(1+i*slope)*(1+.001*(i%11-5))
            arr.append({"day":day,"o":c*1.0003,"h":c*1.01,
                        "l":c*.99,"c":c,"v":1000,
                        "ret60":.04 if slope>0 else -.04,
                        "ema200":c*.90 if slope>0 else c*1.10})
        packs[sym]={"daily":arr,"day_keys":[x["day"] for x in arr]}
    return packs


SYMS=["BTCUSDT","ETHUSDT","SOLUSDT"]
DAY="2024-10-01"

class TacticalV14Tests(unittest.TestCase):
    def test_six_predeclared_arms(self):
        self.assertEqual(len(new.V14_MODES),6)
        self.assertEqual(len(set(new.V14_MODES)),6)
        self.assertTrue(all(x not in old.MODES for x in new.V14_MODES))

    def test_all_v12_modes_replay_exactly_on_original_data(self):
        p=make_packs()
        for mode in old.MODES:
            x=old.simulate(p,"crypto",mode,"2024-06-01","2024-12-01",
                           symbols=SYMS)
            y=new.simulate(p,"crypto",mode,"2024-06-01","2024-12-01",
                           symbols=SYMS)
            self.assertEqual(x["ledger"],y["ledger"],mode)
            self.assertEqual(x["curve"],y["curve"],mode)
            for key,val in x["metrics"].items():
                self.assertEqual(val,y["metrics"][key],(mode,key))

    def test_prior_day_not_today_decision(self):
        p=make_packs()
        before={mode:new.weights(mode,"crypto",DAY,p,SYMS,"BTCUSDT",
                            set(SYMS)) for mode in new.V14_MODES}
        for s in p:
            for bar in p[s]["daily"]:
                if bar["day"]>=DAY:
                    bar["c"]*=100
                    bar["ema200"]*=100
                    bar["ret60"]=-100
        after={mode:new.weights(mode,"crypto",DAY,p,SYMS,"BTCUSDT",
                            set(SYMS)) for mode in new.V14_MODES}
        self.assertEqual(before,after)

    def test_no_allocation_against_market_regime(self):
        p=make_packs()
        for bar in p["BTCUSDT"]["daily"]:
            bar["ema200"]=bar["c"]*1.5
        for mode in new.V14_MODES:
            w=new.weights(mode,"crypto",DAY,p,SYMS,"BTCUSDT",
                           set(SYMS))
            self.assertEqual(w,{},mode)

    def test_prewritten_gross_and_name_caps(self):
        p=make_packs()
        for mode in new.V14_MODES:
            w=new.weights(mode,"crypto",DAY,p,SYMS,"BTCUSDT",set(SYMS))
            self.assertTrue(w,mode)
            self.assertLessEqual(sum(w.values()),.65+1e-10,mode)
            self.assertTrue(all(q<=.30+1e-10 for q in w.values()),mode)

    def test_breadth_lower_when_only_one_asset_trends(self):
        p=make_packs()
        all_weights=new.weights("v14_breadth","crypto",DAY,p,SYMS,
                                "BTCUSDT",set(SYMS))
        for s in ("ETHUSDT","SOLUSDT"):
            for z in p[s]["daily"]:
                z["ema200"]=z["c"]*1.25
        few_weights=new.weights("v14_breadth","crypto",DAY,p,SYMS,
                                "BTCUSDT",set(SYMS))
        self.assertGreater(sum(all_weights.values()),sum(few_weights.values()))
        self.assertLessEqual(sum(few_weights.values()),.30+1e-10)

    def test_dual_horizon_rejects_long_window_loser(self):
        p=make_packs()
        # Make SOL's earliest lookback close unusually high, while
        # the latest 63-day momentum and EMA filter remain positive.
        idx=p["SOLUSDT"]["day_keys"].index(DAY)-1
        p["SOLUSDT"]["daily"][idx-126]["c"]*=100
        base=new.weights("v14_invvol_55","crypto",DAY,p,SYMS,
                         "BTCUSDT",set(SYMS))
        dual=new.weights("v14_dual_horizon","crypto",DAY,p,SYMS,
                         "BTCUSDT",set(SYMS))
        self.assertIn("SOLUSDT",base)
        self.assertNotIn("SOLUSDT",dual)

    def test_core_has_benchmark_without_double_counting(self):
        p=make_packs()
        w=new.weights("v14_core_satellite","crypto",DAY,p,SYMS,
                      "BTCUSDT",set(SYMS))
        self.assertAlmostEqual(w["BTCUSDT"],.15)
        self.assertLessEqual(sum(w.values()),.60+1e-9)

    def test_all_portfolios_fully_cash_funded(self):
        p=make_packs()
        for mode in new.V14_MODES:
            res=new.simulate(p,"crypto",mode,"2024-06-01","2024-12-01",
                             symbols=SYMS,cost=.0006)
            self.assertGreaterEqual(min(z["cash"] for z in res["curve"]),-1e-7,mode)
            self.assertLessEqual(max(z["exposure"] for z in res["curve"]),1+1e-8,mode)
            self.assertTrue(all(x["action"] in ("BUY","SELL") for x in res["ledger"]))

    def test_fee_stress_is_worse_than_nominal_in_buy_only_reference(self):
        p=make_packs()
        normal=new.simulate(p,"crypto","benchmark_hold","2024-06-01","2024-12-01",
                            symbols=SYMS,cost=.0006)
        costly=new.simulate(p,"crypto","benchmark_hold","2024-06-01","2024-12-01",
                            symbols=SYMS,cost=.002)
        self.assertLess(costly["metrics"]["total_return_pct"],
                        normal["metrics"]["total_return_pct"])

    def test_bad_mode_rejected(self):
        with self.assertRaises(ValueError):
            new.weights("not_a_mode","crypto",DAY,make_packs(),SYMS,
                        "BTCUSDT",set(SYMS))

if __name__=="__main__":unittest.main()
