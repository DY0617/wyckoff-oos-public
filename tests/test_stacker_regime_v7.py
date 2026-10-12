"""Causal filters, independent benchmark gate and multi-symbol holdout invariants."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stacker_regime_v7_core as v7


def pack(high=False,reverse=False):
    hh=[]
    for i in range(80):
        last=(i==79)
        # signal i=79; ATR/current vol rises, but is already CLOSED.
        h,l,c=(106.,100.,104.) if last else (101.,99.,100.)
        if reverse and last:
            h,l,c=106.,100.,100.2
        hh.append(dict(ct=1000*i+999,h=h,l=l,c=c,
                       atr14=(10. if last and high else 2.),ema20=101.,
                       ema50=100.))
    return {"h4":hh,"h4_closes":[b["ct"] for b in hh],"hour":[]}


def p(sign=1):
    return {"entry_price":100.,"sign":sign,"stop":90. if sign>0 else 110.,
            "tp":104. if sign>0 else 96.,"quantities":[1.,1.25,1.5,1.75],
            "qty":1.,"cost_basis":100.,"fees":.06,"max_risk_budget":150.,
            "fills":[{"qty":1.}]}


def sig(pack):
    return {"signal_t":pack["h4"][-1]["ct"],"side":"LONG","atr":2.}


class TestV7(unittest.TestCase):
    def test_eight_predeclared_modes(self):
        self.assertEqual(len(v7.MODES),8)
        self.assertEqual(len(set(v7.MODES)),8)

    def test_known_completed_four_hour_only(self):
        x=pack(high=True)
        self.assertIsNone(v7.vol_state(x,x["h4"][-1]["ct"]))
        self.assertIsNotNone(v7.vol_state(x,x["h4"][-1]["ct"]+1))

    def test_asset_vol_filter_skips_high_vol(self):
        x=pack(high=True)
        allowed,scale,reason=v7.entry_decision("asset_vol_skip",x,x,
           {"t":x["h4"][-1]["ct"]+1},sig(x),p())
        self.assertFalse(allowed)
        self.assertEqual(reason,"asset_high_vol")

    def test_benchmark_filter_can_disagree_with_asset(self):
        asset=pack(high=False);bench=pack(high=True)
        ts=asset["h4"][-1]["ct"]+1
        ok,_,_=v7.entry_decision("asset_vol_skip",asset,bench,{"t":ts},sig(asset),p())
        self.assertTrue(ok)
        ok,_,reason=v7.entry_decision("benchmark_vol_skip",asset,bench,{"t":ts},sig(asset),p())
        self.assertFalse(ok)
        self.assertEqual(reason,"benchmark_high_vol")
        ok,_,reason=v7.entry_decision("either_vol_skip",asset,bench,{"t":ts},sig(asset),p())
        self.assertFalse(ok)

    def test_rejection_uses_completed_signal_bar_not_future(self):
        x=pack(reverse=True)
        ts=x["h4"][-1]["ct"]
        state=v7.signal_bar_state(x,ts,1)
        self.assertLess(state["clv"],.35)
        ok,_,reason=v7.entry_decision("bb_rejection",x,x,{"t":ts+1},sig(x),p())
        self.assertFalse(ok)
        self.assertEqual(reason,"no_reversal_wick")
        # A future, unconfirmed extreme must not revise prior bar decision.
        x["h4"].append(dict(ct=ts+1000,h=900,l=1,c=450,atr14=1))
        x["h4_closes"].append(ts+1000)
        self.assertEqual(state,v7.signal_bar_state(x,ts,1))

    def test_short_rejection_is_mirrored(self):
        x=pack(reverse=False)
        ts=x["h4"][-1]["ct"]
        q=v7.signal_bar_state(x,ts,-1)
        self.assertAlmostEqual(q["clv"],(106-104)/(106-100))

    def test_shock_filter(self):
        x=pack()
        x["h4"][-1]["atr14"]=2
        x["h4"][-1]["h"]=112
        x["h4"][-1]["l"]=99
        ts=x["h4"][-1]["ct"]+1
        ok,_,reason=v7.entry_decision("shock_skip",x,x,{"t":ts},sig(x),p())
        self.assertFalse(ok)
        self.assertEqual(reason,"extreme_signal_range")

    def test_graded_size_never_adds_leverage(self):
        asset=pack(high=True);ts=asset["h4"][-1]["ct"]+1
        ok,scale,_=v7.entry_decision("graded_size",asset,asset,{"t":ts},sig(asset),p())
        self.assertTrue(ok)
        self.assertEqual(scale,.5)
        q=p()
        v7.scale_position(q,scale)
        self.assertEqual(q["quantities"],[.5,.625,.75,.875])
        self.assertAlmostEqual(q["max_risk_budget"],75.)

    def test_default_control_does_not_filter(self):
        x=pack(high=True)
        ok,scale,label=v7.entry_decision("control",x,x,
                                  {"t":x["h4"][-1]["ct"]+1},sig(x),p())
        self.assertTrue(ok)
        self.assertEqual(scale,1.)

    def test_holdout_symbols_explicitly_selected(self):
        fake={"BTCUSDT":{"hour":[]},"SOLUSDT":{"hour":[]},"ETHUSDT":{"hour":[]}}
        with patch.object(v7.structure,"build_signals",return_value={}):
            z=v7.simulate(fake,"crypto","control",0,10000,
                          trade_symbols=["SOLUSDT"])
        self.assertEqual(z["metrics"]["trades"],0)
        self.assertEqual(z["metrics"]["net_return_pct"],0)

    def test_missing_asset_not_silently_substituted(self):
        fake={"BTCUSDT":{"hour":[]},"ETHUSDT":{"hour":[]}}
        with self.assertRaises(ValueError):
            v7.simulate(fake,"crypto","control",0,10000,
                        trade_symbols=["SOLUSDT"])

if __name__=="__main__":unittest.main()
