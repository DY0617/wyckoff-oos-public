"""V12 strict spot source, cash-only weekly/capped/crashguard invariants."""
import sys,unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import tactical_allocation_v11_core as old
import tactical_allocation_v12_core as new
import verified_spot_v12 as spot

UTC=timezone.utc


def prices(n=700,second_down=False):
    start=date(2023,1,1)
    packs={}
    for sym,decline in (("BTCUSDT",False),("ETHUSDT",second_down)):
        rows=[]
        for i in range(n):
            day=(start+timedelta(days=i)).isoformat()
            c=100*(1+(.001*i if not decline else -.00045*i))
            c*=1+((i%13)-6)*.001
            rows.append({"day":day,"o":c*(1+.002*((i%5)-2)),
                         "h":c*1.01,"l":c*.99,"c":c,
                         "v":1000,
                         "ema200":c*.90 if not decline else c*1.1,
                         "ret60":.06 if not decline else -.06})
        packs[sym]={"daily":rows,"day_keys":[x["day"] for x in rows]}
    return packs


class VerifiedSpot(unittest.TestCase):
    def test_market_source_is_true_spot(self):
        self.assertIn("/spot/monthly/",spot.SPOT_URL)
        self.assertNotIn("/futures/",spot.SPOT_URL)

    def test_timestamp_microsecond_normalized_and_checked(self):
        s="open_time,open,high,low,close,volume\n1704067200000000,100,110,90,105,40\n"
        z=spot.rows_from_archive(s,"BTCUSDT",
                   datetime(2024,1,1,tzinfo=UTC),datetime(2024,1,2,tzinfo=UTC))
        self.assertEqual(len(z),1)
        self.assertEqual(z[0]["day"],"2024-01-01")
        self.assertEqual(z[0]["c"],105)

    def test_duplicate_daily_open_rejected(self):
        s="1704067200000,100,105,95,102,10\n1704067200000,100,105,95,102,10\n"
        with self.assertRaises(ValueError):
            spot.rows_from_archive(s,"BTCUSDT",datetime(2024,1,1,tzinfo=UTC),
                                   datetime(2024,1,2,tzinfo=UTC))

    def test_bad_candle_rejected(self):
        s="1704067200000,100,96,95,102,10\n"
        with self.assertRaises(ValueError):
            spot.rows_from_archive(s,"BTCUSDT",datetime(2024,1,1,tzinfo=UTC),
                                   datetime(2024,1,2,tzinfo=UTC))

    def test_no_silent_forward_filling_gaps(self):
        start=datetime(2024,1,1,tzinfo=UTC)
        z=[{"t":int((start+timedelta(days=k)).timestamp()*1000),
            "o":100,"h":101,"l":99,"c":100,"v":1,
            "day":(start+timedelta(days=k)).date().isoformat()}
           for k in (0,2)]
        with self.assertRaises(ValueError):
            spot.build_daily_pack(z,"BTCUSDT",start,start+timedelta(days=3))

    def test_daily_indicators_are_computed_only_on_daily(self):
        start=datetime(2024,1,1,tzinfo=UTC)
        z=[{"t":int((start+timedelta(days=k)).timestamp()*1000),
            "o":100+k*.1,"h":102+k*.1,"l":99+k*.1,"c":100+k*.1,"v":1,
            "day":(start+timedelta(days=k)).date().isoformat()}
           for k in range(250)]
        p=spot.build_daily_pack(z,"BTCUSDT",start,start+timedelta(days=250))
        self.assertIsNone(p["daily"][199]["ema200"])
        self.assertIsNotNone(p["daily"][200]["ema200"])
        self.assertEqual(len(p["daily"]),250)


class TacticalDefense(unittest.TestCase):
    def test_new_modes_exist(self):
        self.assertEqual(set(new.MODES)-set(old.MODES),
                         {"gate_weekly","gate_cap","gate_crashguard"})

    def test_exact_v11_portfolio_and_trade_parity_for_seven_arms(self):
        p=prices(second_down=True)
        for mode in old.MODES:
            a=old.simulate(p,"crypto",mode,"2024-03-01","2024-11-01",
                           symbols=["BTCUSDT","ETHUSDT"])
            b=new.simulate(p,"crypto",mode,"2024-03-01","2024-11-01",
                           symbols=["BTCUSDT","ETHUSDT"])
            self.assertEqual(a["metrics"]["total_return_pct"],
                             b["metrics"]["total_return_pct"],mode)
            self.assertEqual(a["ledger"],b["ledger"],mode)
            self.assertEqual(a["curve"],b["curve"],mode)

    def test_cap_never_adds_leverage_or_concentration(self):
        p=prices()
        day="2024-05-01"
        w=new.weights("gate_cap","crypto",day,p,
                      ["BTCUSDT","ETHUSDT"],"BTCUSDT",
                      {"BTCUSDT","ETHUSDT"})
        self.assertLessEqual(sum(w.values()),.50+1e-8)
        self.assertTrue(all(z<=.20+1e-8 for z in w.values()))

    def test_cash_yield_applies_only_to_uninvested_balance(self):
        p=prices(second_down=True)
        for mode in ("gate_cap","gate_crashguard"):
            z=new.simulate(p,"crypto",mode,"2024-03-01","2024-11-01",
                           symbols=["BTCUSDT","ETHUSDT"])
            self.assertGreaterEqual(min(t["cash"] for t in z["curve"]),-1e-7)
            self.assertLessEqual(max(t["exposure"] for t in z["curve"]),1.000001)
        # Completely cash-only gate produces growth from interest,
        # despite 0% gross risk exposure.
        for b in p["BTCUSDT"]["daily"]:
            b["ema200"]=b["c"]*1.3
            b["ret60"]=-.4
        a=new.simulate(p,"crypto","risk_managed_gate",
                       "2024-03-01","2024-11-01",
                       symbols=["BTCUSDT","ETHUSDT"])
        b=new.simulate(p,"crypto","risk_managed_gate",
                       "2024-03-01","2024-11-01",
                       symbols=["BTCUSDT","ETHUSDT"],cash_annual_yield=.03)
        self.assertEqual(a["metrics"]["total_return_pct"],0)
        self.assertGreater(b["metrics"]["total_return_pct"],0)

    def test_weekly_has_distinct_rebalance_timing(self):
        p=prices()
        wk=new.simulate(p,"crypto","gate_weekly",
                        "2024-03-01","2024-11-01",symbols=["BTCUSDT","ETHUSDT"])
        mo=new.simulate(p,"crypto","risk_managed_gate",
                        "2024-03-01","2024-11-01",symbols=["BTCUSDT","ETHUSDT"])
        self.assertGreaterEqual(len(wk["ledger"]),len(mo["ledger"]))
        # Does not require trading every week (1% no-trade band).
        self.assertTrue(all(t["date"] in p["BTCUSDT"]["day_keys"] for t in wk["ledger"]))

    def test_crashguard_uses_only_previous_completed_day(self):
        p=prices()
        day="2024-05-01"
        base=new.weights("gate_crashguard","crypto",day,p,
                         ["BTCUSDT","ETHUSDT"],"BTCUSDT",
                         {"BTCUSDT","ETHUSDT"})
        idx=p["BTCUSDT"]["day_keys"].index(day)
        p["BTCUSDT"]["daily"][idx]["c"]=0.01
        after=new.weights("gate_crashguard","crypto",day,p,
                          ["BTCUSDT","ETHUSDT"],"BTCUSDT",
                          {"BTCUSDT","ETHUSDT"})
        self.assertEqual(base,after)

    def test_unsupported_cash_rate_fails_fast(self):
        with self.assertRaises(ValueError):
            new.simulate(prices(),"crypto","gate_cap","2024-05-01","2024-07-01",
                         symbols=["BTCUSDT","ETHUSDT"],cash_annual_yield=-.03)

if __name__=="__main__":unittest.main()
