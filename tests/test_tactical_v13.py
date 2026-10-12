"""V13 daily next-open drift-cap invariants + benchmark-cash parity."""
import sys,unittest
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import tactical_allocation_v12_core as old
import tactical_allocation_v13_core as new


def history():
    start=date(2023,1,1)
    packs={}
    for sym in ("BTCUSDT","ETHUSDT"):
        rows=[]
        for i in range(570):
            d=(start+timedelta(days=i)).isoformat()
            c=100+i*.02+(i%9)*.07
            o=c
            if sym=="BTCUSDT" and d>="2024-02-14":
                c*=2.0;o*=2.0
            if sym=="BTCUSDT" and d=="2024-02-14":
                o/=2.0  # intraday jump: prior day close normal, current close doubles
            if sym=="BTCUSDT" and d=="2024-02-15":
                o*=1.2 # gapped open executes at 120% of last close
            rows.append(dict(day=d,o=o,c=c,h=max(o,c)*1.002,
                             l=min(o,c)*.998,ema200=c*.8,ret60=.10,v=1000))
        packs[sym]={"daily":rows,"day_keys":[z["day"] for z in rows]}
    return packs


class TacticalV13Tests(unittest.TestCase):
    def test_modes_and_locked_overlay(self):
        self.assertEqual(set(new.MODES)-set(old.MODES),
           {"gate_cap_daily","passive_25_bench","passive_50_bench"})
        self.assertEqual(new.PARAMS["drift_total_trigger"],.50)
        self.assertEqual(new.PARAMS["drift_asset_trigger"],.20)

    def test_legacy_ten_modes_preserve_trade_ledger_metrics(self):
        p=history()
        for mode in old.MODES:
            old_r=old.simulate(p,"crypto",mode,"2024-02-01","2024-04-01",
                               symbols=["BTCUSDT","ETHUSDT"])
            new_r=new.simulate(p,"crypto",mode,"2024-02-01","2024-04-01",
                               symbols=["BTCUSDT","ETHUSDT"])
            self.assertEqual(old_r["ledger"],new_r["ledger"],mode)
            for k,val in old_r["metrics"].items():
                self.assertEqual(val,new_r["metrics"][k],(mode,k))
            for a,b in zip(old_r["curve"],new_r["curve"]):
                for k,val in a.items():self.assertEqual(val,b[k],(mode,a["day"],k))

    def test_ex_post_day_breach_is_traded_next_open_not_prior_close(self):
        p=history()
        z=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-03-01",
                       symbols=["BTCUSDT","ETHUSDT"],cost=.0006)
        drift=[x for x in z["ledger"] if x.get("reason")=="PRIOR_CLOSE_DRIFT_CAP"]
        self.assertTrue(drift,"must trigger next-day cap reduction")
        first=min(x["date"] for x in drift)
        self.assertEqual(first,"2024-02-15")
        for x in drift:
            candle=next(k for k in p[x["symbol"]]["daily"] if k["day"]==x["date"])
            self.assertEqual(x["price"],candle["o"])
        self.assertLessEqual(next(x for x in z["curve"] if x["day"]=="2024-02-15")["max_name_weight"],.20)

    def test_drift_does_not_reactively_trade_inside_same_day(self):
        p=history()
        z=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-03-01",
                       symbols=["BTCUSDT","ETHUSDT"])
        same_day=[x for x in z["ledger"] if x["date"]=="2024-02-14" and
                  x.get("reason")=="PRIOR_CLOSE_DRIFT_CAP"]
        self.assertEqual(len(same_day),0)

    def test_no_leverage_cash_nonnegative_and_expected_overshoot_count(self):
        p=history()
        z=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-04-01",
                       symbols=["BTCUSDT","ETHUSDT"])
        self.assertGreater(z["metrics"]["events"].get("drift_signals",0),0)
        self.assertGreaterEqual(min(x["cash"] for x in z["curve"]),-1e-8)
        self.assertLessEqual(max(x["exposure"] for x in z["curve"]),1+1e-9)
        self.assertGreater(z["metrics"]["days_name_above_20pct"],0)

    def test_cash_slices_are_hold_and_never_borrow(self):
        p=history()
        for mode,part in (("passive_25_bench",.25),("passive_50_bench",.50)):
            z=new.simulate(p,"crypto",mode,"2024-02-01","2024-04-01",
                           symbols=["BTCUSDT","ETHUSDT"])
            self.assertEqual(len(z["ledger"]),1)
            self.assertEqual(z["ledger"][0]["symbol"],"BTCUSDT")
            self.assertEqual(z["ledger"][0]["action"],"BUY")
            self.assertAlmostEqual(z["ledger"][0]["notional"],20000*part)
            self.assertGreaterEqual(min(x["cash"] for x in z["curve"]),0)
            self.assertLessEqual(max(x["exposure"] for x in z["curve"]),1)

    def test_later_future_prices_never_affect_prior_day_drifts(self):
        p=history()
        a=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-02-18",
                       symbols=["BTCUSDT","ETHUSDT"])
        for s in p:
            for x in p[s]["daily"]:
                if x["day"]>"2024-02-17":
                    x["c"]*=100;x["o"]*=100
        b=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-02-18",
                       symbols=["BTCUSDT","ETHUSDT"])
        self.assertEqual(a["ledger"],b["ledger"])
        self.assertEqual(a["metrics"],b["metrics"])

    def test_fee_stress_reduces_cash_after_same_exits(self):
        p=history()
        base=new.simulate(p,"crypto","passive_25_bench","2024-02-01","2024-04-01",
                          symbols=["BTCUSDT","ETHUSDT"],cost=.0006)
        stress=new.simulate(p,"crypto","passive_25_bench","2024-02-01","2024-04-01",
                            symbols=["BTCUSDT","ETHUSDT"],cost=.0020)
        self.assertLess(stress["metrics"]["total_return_pct"],
                        base["metrics"]["total_return_pct"])

    def test_missed_stock_execution_does_not_sell_at_last_close(self):
        p=history()
        # In the absence of the stock's new-day OPEN, a previously
        # breached limit must not fabricate a next-session fill.
        missing="2024-02-15"
        p["BTCUSDT"]["daily"]=[z for z in p["BTCUSDT"]["daily"] if z["day"]!=missing]
        p["BTCUSDT"]["day_keys"]=[z["day"] for z in p["BTCUSDT"]["daily"]]
        z=new.simulate(p,"crypto","gate_cap_daily","2024-02-01","2024-03-01",
                       symbols=["BTCUSDT","ETHUSDT"])
        self.assertFalse(any(t["symbol"]=="BTCUSDT" and t["date"]==missing
                             for t in z["ledger"]))
        self.assertGreater(z["metrics"]["events"].get("drift_halted_symbol",0),0)

if __name__=="__main__":unittest.main()
