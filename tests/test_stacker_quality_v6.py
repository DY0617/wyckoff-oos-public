"""Pure offline invariants for Stacker v6 quality and risk controls."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stacker_quality_v6_core as v6


def p():
    return {"sign":1,"entry_price":100.,"stop":90.,
            "tp":107.,"quantities":[1.,1.2,1.5,1.8],
            "qty":1.,"cost_basis":100.,"fees":.06,
            "max_risk_budget":150.,"fills":[{"qty":1.,"price":100.}]}


def pack(high=False):
    bars=[{"ct":k*100000+100,"c":100.,"atr14":2.} for k in range(80)]
    if high:bars[-1]["atr14"]=5.
    return {"h4":bars,"h4_closes":[x["ct"] for x in bars]}


def daypack():
    rows=[]
    for i in range(7):
        rows.append({"day":"2025-01-%02d"%(i+1),"c":110.,
                     "ema50":100.+i,"ema200":90.})
    return {"day_keys":[x["day"] for x in rows],"daily":rows}


def entrybar():
    return {"t":8_000_000,"day":"2025-01-08","o":100.}


class V6InvariantTests(unittest.TestCase):
    def test_seven_disjoint_ablation_names(self):
        self.assertEqual(len(v6.MODES),7)
        self.assertEqual(len(set(v6.MODES)),7)

    def test_htf_excludes_current_not_closed(self):
        x=pack(True)
        # before final 4H candle closes, 80-bar volatility sample absent
        self.assertIsNone(v6.vol_state(x,x["h4_closes"][-1]))
        self.assertEqual(v6.completed_h4_index(x,x["h4_closes"][-1]),78)

    def test_vol_gate_flags_upper_quintile(self):
        x=pack(True)
        v=v6.vol_state(x,x["h4_closes"][-1]+1)
        self.assertTrue(v["high"])
        self.assertGreater(v["current"],v["p80"])

    def test_vol_scale_halves_notional_if_high(self):
        x=pack(True)
        with patch.object(v6,"vol_state",return_value={"high":True}):
            ok,scale,reason=v6.entry_decision(
                "vol_scale",x,None,entrybar(),{},p())
        self.assertTrue(ok)
        self.assertEqual(scale,.5)

    def test_vol_skip_rejects_same_setup(self):
        with patch.object(v6,"vol_state",return_value={"high":True}):
            ok,scale,reason=v6.entry_decision(
                "vol_skip",None,None,entrybar(),{},p())
        self.assertFalse(ok)
        self.assertEqual(reason,"high_vol")

    def test_reward_floor_is_independent_of_fees(self):
        self.assertAlmostEqual(v6.first_r_at_target(p()),.7)
        with patch.object(v6,"first_r_at_target",return_value=.50):
            ok,scale,reason=v6.entry_decision(
                "reward_floor",None,None,entrybar(),{},p())
        self.assertEqual(reason,"target_too_close")
        self.assertFalse(ok)

    def test_daily_filter_only_uses_previous_day(self):
        asset=daypack();benchmark=daypack()
        self.assertTrue(v6.daily_trend_ok(asset,benchmark,entrybar(),1))
        asset["daily"][-1]["ema50"]=5.
        asset["daily"][-1]["c"]=1.
        # Jan 7 is yesterday; today's deliberately hostile hypothetical
        # daily bar (Jan 8) must not influence Jan 8 entry.
        self.assertFalse(v6.daily_trend_ok(asset,benchmark,entrybar(),1))

    def test_short_uses_opposite_daily_sign(self):
        a=daypack();b=daypack()
        self.assertFalse(v6.daily_trend_ok(a,b,entrybar(),-1))

    def test_risk_scaling_preserves_stop_and_tp(self):
        x=p();stop=x["stop"];tp=x["tp"]
        v6.scale_position(x,.5)
        self.assertEqual(x["stop"],stop)
        self.assertEqual(x["tp"],tp)
        self.assertEqual(x["quantities"],[.5,.6,.75,.9])
        self.assertAlmostEqual(x["max_risk_budget"],75.)
        self.assertAlmostEqual(x["fills"][0]["qty"],.5)
        self.assertAlmostEqual(x["fees"],.03)

    def test_scale_raises_if_increase_risk(self):
        with self.assertRaises(ValueError):
            v6.scale_position(p(),1.05)

    def test_combo_requires_all_gates(self):
        with patch.object(v6,"daily_trend_ok",return_value=True),patch.object(
            v6,"vol_state",return_value={"high":False}):
            ok,scale,_=v6.entry_decision("quality_combo",None,None,entrybar(),{},p())
        self.assertTrue(ok)
        with patch.object(v6,"daily_trend_ok",return_value=True),patch.object(
            v6,"vol_state",return_value={"high":True}):
            ok,scale,reason=v6.entry_decision("quality_combo",None,None,entrybar(),{},p())
        self.assertFalse(ok)
        self.assertEqual(reason,"high_vol")

if __name__=="__main__":unittest.main()
