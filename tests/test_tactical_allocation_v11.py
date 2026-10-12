"""Adversarial invariants for strategic, cash-only tactical allocation."""
import sys,unittest
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import tactical_allocation_v11_core as m


def asset(name,multiplier=1.0,reverse=False):
    start=date(2024,1,1)
    rows=[]
    for i in range(400):
        d=(start+timedelta(days=i)).isoformat()
        factor=(1+i*.002 if not reverse else max(.30,1-i*.0015))
        noise=1+(i%7-3)*.001
        close=100*multiplier*factor*noise
        op=close*(1+.0004*(i%3-1))
        rows.append({"day":d,"t":i*86400000,"ct":(i+1)*86400000-1,
                     "o":op,"h":max(close,op)*1.001,"l":min(close,op)*.999,
                     "c":close,"v":1000,"ema200":close*.95 if not reverse else close*1.05,
                     "ret60":.05 if not reverse else -.06})
    return {"daily":rows,"day_keys":[x["day"] for x in rows]}


def data(reverse_b=False):
    return {"BTCUSDT":asset("BTC",1),
            "ETHUSDT":asset("ETH",2,reverse_b)}


class TacticalV11Tests(unittest.TestCase):
    def test_seven_predeclared_portfolio_arms(self):
        self.assertEqual(len(m.MODES),7)
        self.assertEqual(len(set(m.MODES)),7)

    def test_prior_day_excludes_current_close_and_future_prices(self):
        p=data();d=p["BTCUSDT"]["day_keys"][300]
        c1=m.make_context(p,"crypto",d,["BTCUSDT","ETHUSDT"],"BTCUSDT")
        self.assertEqual(c1["BTCUSDT"]["prev_day"],p["BTCUSDT"]["day_keys"][299])
        p["BTCUSDT"]["daily"][300]["c"]*=30
        p["BTCUSDT"]["daily"][300]["ema200"]*=30
        p["BTCUSDT"]["daily"][330]["c"]*=10
        c2=m.make_context(p,"crypto",d,["BTCUSDT","ETHUSDT"],"BTCUSDT")
        self.assertEqual(c1,c2)

    def test_monthly_rebalance_at_daily_open_only(self):
        p=data()
        x=m.simulate(p,"crypto","equal_monthly",
                     "2024-09-01","2025-01-01",symbols=["BTCUSDT","ETHUSDT"])
        traded_days=[r["date"] for r in x["ledger"]]
        self.assertTrue(traded_days)
        self.assertTrue(all(x[:7] in ("2024-09","2024-10","2024-11","2024-12")
                            for x in traded_days))
        self.assertEqual(len(set(x[:7] for x in traded_days)),4)
        self.assertTrue(all(r["price"]==next(z["o"] for z in p[r["symbol"]]["daily"]
                                   if z["day"]==r["date"]) for r in x["ledger"]))

    def test_cash_conservation_and_total_exposure_cap(self):
        p=data()
        for mode in m.MODES:
            a=m.simulate(p,"crypto",mode,"2024-09-01","2025-02-01",
                         symbols=["BTCUSDT","ETHUSDT"])
            self.assertGreaterEqual(min(z["cash"] for z in a["curve"]),-1e-7,mode)
            self.assertLessEqual(max(z["exposure"] for z in a["curve"]),1.000001,mode)
            self.assertGreaterEqual(a["metrics"]["execution_count"],0,mode)

    def test_hold_only_buys_and_no_monthly_churn(self):
        p=data()
        a=m.simulate(p,"crypto","equal_hold","2024-09-01","2025-01-01",
                     symbols=["BTCUSDT","ETHUSDT"])
        self.assertEqual(a["metrics"]["execution_count"],2)
        self.assertTrue(all(r["action"]=="BUY" for r in a["ledger"]))

    def test_cash_is_valid_position_when_regime_is_weak(self):
        p=data(reverse_b=True)
        # Also put BTC benchmark in bad regime.
        for d in p["BTCUSDT"]["daily"]:
            d["ema200"]=d["c"]*1.05
            d["ret60"]=-.05
        a=m.simulate(p,"crypto","risk_managed_gate",
                     "2024-09-01","2025-01-01",
                     symbols=["BTCUSDT","ETHUSDT"])
        self.assertEqual(a["metrics"]["execution_count"],0)
        self.assertAlmostEqual(a["metrics"]["final_equity"],20000)
        self.assertAlmostEqual(a["metrics"]["avg_exposure"],0)

    def test_eligible_assets_are_selected_by_prior_return(self):
        p=data(reverse_b=True)
        day=p["BTCUSDT"]["day_keys"][300]
        for mode in ("absolute_trend","momentum_top","risk_managed","risk_managed_gate"):
            w=m.weights(mode,"crypto",day,p,["BTCUSDT","ETHUSDT"],
                        "BTCUSDT",{"BTCUSDT","ETHUSDT"})
            self.assertTrue(w.get("BTCUSDT",0)>0,mode)
            self.assertEqual(w.get("ETHUSDT",0),0,mode)

    def test_cost_increase_does_not_improve_one_way_buy_and_hold(self):
        p=data()
        a=m.simulate(p,"crypto","equal_hold","2024-09-01","2025-01-01",
                     cost=.0006,symbols=["BTCUSDT","ETHUSDT"])
        b=m.simulate(p,"crypto","equal_hold","2024-09-01","2025-01-01",
                     cost=.0010,symbols=["BTCUSDT","ETHUSDT"])
        self.assertLess(b["metrics"]["total_return_pct"],
                        a["metrics"]["total_return_pct"])

    def test_benchmark_hold_purchases_only_benchmark(self):
        p=data()
        a=m.simulate(p,"crypto","benchmark_hold","2024-09-01","2025-01-01",
                     symbols=["BTCUSDT","ETHUSDT"])
        self.assertEqual(set(z["symbol"] for z in a["ledger"]),{"BTCUSDT"})

    def test_never_use_future_at_rebalance_even_if_current_prices_spike(self):
        p=data()
        d=p["BTCUSDT"]["day_keys"][300]
        w=m.weights("risk_managed","crypto",d,p,["BTCUSDT","ETHUSDT"],
                    "BTCUSDT",{"BTCUSDT","ETHUSDT"})
        for s in p:
            p[s]["daily"][301]["o"]*=10000
            p[s]["daily"][301]["c"]*=10000
        w2=m.weights("risk_managed","crypto",d,p,["BTCUSDT","ETHUSDT"],
                     "BTCUSDT",{"BTCUSDT","ETHUSDT"})
        self.assertEqual(w,w2)

    def test_invalid_or_overlevered_target_rejected(self):
        with self.assertRaises(AssertionError):
            m.diagnostics("",-10,{},{})

if __name__=="__main__":unittest.main()
