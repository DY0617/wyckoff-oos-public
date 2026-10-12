"""Pure offline tests for v10 breakout causality and v8 execution parity."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import entry_expansion_v10_core as v10
import entry_first_v8_core as v8


MS=3600000

def make_pack():
    hh=[]
    for i in range(94):
        t=i*4*MS
        x=dict(t=t,ct=t+4*MS-1,o=100,h=101,l=99,c=100,
               atr14=4,ema20=100,ema50=100,ema200=100,
               day="2025-01-02",v=40,count=4)
        hh.append(x)
    hh[90].update(o=100,h=107,l=99,c=106,v=80)
    # Future price must not alter earlier signals.
    bars=[]
    for j in range(94*4):
        b=dict(t=j*MS,ct=(j+1)*MS-1,o=100,h=101,l=99,c=100,
               atr14=2,ema20=100,day="2025-01-02",v=10)
        bars.append(b)
    bars[90*4+3].update(o=103,h=107,l=102,c=106)
    bars[91*4].update(o=106,h=108,l=105,c=107)
    daily=[
      dict(day="2025-01-01",c=115,ema200=100,ema50=110,ret20=.10),
      dict(day="2025-01-02",c=80,ema200=100,ema50=80,ret20=-.20)
    ]
    return dict(hour=bars,h4=hh,h4_closes=[x["ct"] for x in hh],
                daily=daily,day_keys=[z["day"] for z in daily])


class ExpansionV10Tests(unittest.TestCase):
    def test_eight_frozen_modes(self):
        self.assertEqual(len(v10.MODES),8)
        self.assertEqual(len(set(v10.MODES)),8)

    def test_closed_breakout_prior_20_highs_and_not_current_high(self):
        p=make_pack()
        entries=v10.directional_breakout(p["h4"],90,"stock")
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["side"],"LONG")
        self.assertEqual(entries[0]["breakout_level"],101)
        p["h4"][90]["c"]=101.1
        self.assertEqual(v10.directional_breakout(p["h4"],90,"stock"),[])

    def test_stock_does_not_short_but_crypto_can(self):
        p=make_pack()
        p["h4"][90].update(h=101,l=93,c=94)
        self.assertEqual(v10.directional_breakout(p["h4"],90,"stock"),[])
        z=v10.directional_breakout(p["h4"],90,"crypto")
        self.assertEqual(z[0]["side"],"SHORT")

    def test_compression_uses_prebreak_only(self):
        p=make_pack()
        r=v10.compression_readings(p["h4"])
        ok=v10.squeeze_at(r,90)
        p["h4"][90]["h"]=1000000
        newer=v10.compression_readings(p["h4"])
        self.assertEqual(ok,v10.squeeze_at(newer,90))
        self.assertEqual(ok,True)

    def test_volume_per_1h_normalizes_stock_chunk_length(self):
        base={"v":40,"count":4}
        half={"v":20,"count":2}
        self.assertEqual(v10.normalized_volume(base),v10.normalized_volume(half))
        p=make_pack()
        self.assertTrue(v10.participation_at(p["h4"],90))
        p["h4"][90]["v"]=30
        self.assertFalse(v10.participation_at(p["h4"],90))

    def test_previous_daily_not_current_daily(self):
        b=make_pack()
        self.assertTrue(v10.prior_day_market_ok(b,"2025-01-02",1))
        b["daily"][1]["ema200"]=999
        self.assertTrue(v10.prior_day_market_ok(b,"2025-01-02",1))

    def test_relative_strength_and_benchmark_self(self):
        p=make_pack()
        p["daily"][0]["ret20"]=.15
        b=make_pack();b["daily"][0]["ret20"]=.10
        self.assertTrue(v10.prior_day_rs_ok(p,b,"2025-01-02",1))
        self.assertFalse(v10.prior_day_rs_ok(p,b,"2025-01-02",-1))
        self.assertTrue(v10.prior_day_rs_ok(b,b,"2025-01-02",1,True))

    def test_full_signal_next_hour_open_only(self):
        p=make_pack()
        signalbank=v10.precompute_signals(p,p,"crypto",True)
        target=(91*4)*MS
        self.assertIn(target,signalbank["range_break"])
        self.assertNotIn((90*4+3)*MS,signalbank["range_break"])
        z=signalbank["range_break"][target]
        self.assertEqual(z["signal_t"],p["h4"][90]["ct"])
        self.assertEqual(z["entry_atr"],2)

    def test_followthrough_enters_one_hour_later(self):
        p=make_pack()
        out=v10.precompute_signals(p,p,"stock",False)
        breakout_t=91*4*MS
        self.assertIn(breakout_t,out["range_break"])
        self.assertNotIn(breakout_t,out["followthrough"])
        self.assertIn(breakout_t+MS,out["followthrough"])
        self.assertEqual(out["followthrough"][breakout_t+MS]["signal_t"],
                         p["hour"][91*4]["ct"])

    def test_future_bar_does_not_change_prior_signal(self):
        p=make_pack()
        a=v10.precompute_signals(p,p,"stock")
        t=91*4*MS
        before=a["range_break"][t].copy()
        p["h4"][93].update(h=4000,l=0.01,c=300)
        p["hour"][-1].update(h=9999,l=1,c=8999)
        b=v10.precompute_signals(p,p,"stock")
        self.assertEqual(before,b["range_break"][t])

    def test_volume_filter_uses_complete_signal_bar(self):
        p=make_pack()
        d=v10.precompute_signals(p,p,"stock")
        t=91*4*MS
        self.assertIn(t,d["volume_confirm"])
        p["h4"][90]["v"]=30
        d=v10.precompute_signals(p,p,"stock")
        self.assertNotIn(t,d["volume_confirm"])
        self.assertIn(t,d["range_break"])

    def test_stop_and_cost_budget_inherit_v8_execution(self):
        p=make_pack();bank=v10.precompute_signals(p,p,"stock")
        s=bank["range_break"][91*4*MS]
        entry,why=v8.open_trade("TEST","range_break",s,p["hour"][91*4],20000,.0006)
        self.assertIsNotNone(entry,why)
        self.assertAlmostEqual(entry["target"]-entry["entry"],
                               2*(entry["entry"]-entry["stop"]))
        self.assertLessEqual(entry["qty"]*(entry["risk_price"]+
                   .001*(entry["entry"]+entry["stop"])),100.001)
        self.assertLessEqual(entry["qty"]*entry["entry"],14000.001)

    def test_portfolio_wrapper_matches_direct_v8(self):
        p=make_pack()
        bank=v10.precompute_signals(p,p,"crypto",True)
        lo=p["hour"][0]["t"];hi=p["hour"][-1]["ct"]+1
        wrapped=v10.simulate({"BTCUSDT":p},"crypto","range_break",lo,hi,
            trade_symbols=["BTCUSDT"],
            precomputed={"BTCUSDT":bank})
        bare=v8.simulate({"BTCUSDT":p},"crypto","sweep",lo,hi,
             trade_symbols=["BTCUSDT"],
             precomputed={"BTCUSDT":{"sweep":bank["range_break"]}})
        self.assertEqual(wrapped["metrics"],bare["metrics"])
        self.assertEqual(len(wrapped["trades"]),len(bare["trades"]))

if __name__=="__main__":unittest.main()
