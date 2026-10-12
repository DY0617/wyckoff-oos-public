"""Isolated frozen v4 Stacker ablation invariants, pure offline tests."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import stacker_rotation_v3_core as old
import stacker_rotation_v4_core as new


def setup():
    return {"side":"LONG","atr":2.0,"signal_t":0,
            "structure":{"pivot_low":[91.],"pivot_high":[109.],
              "ema20":103.0,"ema50":105.0,"structure_t":-1}}


def bar(t=0,o=100,h=101,l=99,c=100):
    return dict(t=t,ct=t+3_600_000-1,o=o,h=h,l=l,c=c,day="2025-01-01")


def pos(mode):
    p=new.position_from_signal("BTCUSDT","crypto",setup(),100,0,20000,.0006,mode)
    assert p is not None
    p["mode"]=mode
    return p


def do_first_tp(p,mode):
    assert new.process_bar(p,bar(),"crypto",mode,.0006,{},entry_bar=True) is None
    assert new.process_bar(p,bar(3_600_000,100,104,99,103),
                           "crypto",mode,.0006,{}) is None
    assert p["cycle_phase"]=="WAIT_REBUY"


class TestStackerV4(unittest.TestCase):
    def test_variants_are_predeclared(self):
        self.assertEqual(len(new.MODES),7)
        self.assertEqual(len(set(new.MODES)),7)

    def test_control_static_parity(self):
        x=old.position_from_signal("BTCUSDT","crypto",setup(),100,0,20000,.0006)
        y=pos("static")
        self.assertEqual(x["quantities"],y["quantities"])
        self.assertEqual(x["levels"],y["levels"])
        self.assertEqual(x["stop"],y["stop"])
        self.assertEqual(x["tp"],y["tp"])

    def test_slim_ladder_same_max_risk(self):
        p=pos("light_ladder")
        self.assertEqual(p["levels"],[100,96])
        self.assertEqual(len(p["quantities"]),2)
        worst=sum(q*((px-p["stop"])+.001*(px+p["stop"]))
                  for q,px in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(worst,p["max_risk_budget"]+1e-5)
        self.assertAlmostEqual(worst,p["max_risk_budget"],delta=1)

    def test_confirm_requires_previous_closed_bar(self):
        p=pos("confirm_support")
        do_first_tp(p,"confirm_support")
        # Touch happens IN this bar, but rejection is only known at its CLOSE.
        with patch.object(new,"do_rebuy",return_value=True) as rebuy:
            new.process_bar(p,bar(7_200_000,103,103,100,102.8),"crypto",
                            "confirm_support",.0006,{})
            self.assertEqual(p["cycle_phase"],"WAIT_REBUY")
            self.assertEqual(p["confirm_pending"],10_799_999)
            rebuy.assert_not_called()
            new.process_bar(p,bar(10_800_000,102,104,100,103),"crypto",
                            "confirm_support",.0006,{})
            rebuy.assert_called_once()
            self.assertEqual(rebuy.call_args.args[1],102)

    def test_rejection_has_directional_clv_filter(self):
        p=pos("confirm_support")
        do_first_tp(p,"confirm_support")
        new.process_bar(p,bar(7_200_000,103,104,100,101.7),
                        "crypto","confirm_support",.0006,{})
        self.assertIsNone(p["confirm_pending"])

    def test_4h_momentum_cannot_use_incomplete_bar(self):
        pack={"h4_closes":[999,1999,2999],
              "h4":[{"ema20":99,"ema50":100,"c":100},
                     {"ema20":100,"ema50":99,"c":101},
                     {"ema20":95,"ema50":105,"c":96}]}
        self.assertTrue(new.trend_reentry_ok(pack,2500,1))
        self.assertFalse(new.trend_reentry_ok(pack,3500,1))

    def test_profit_protection_raises_long_stop_after_tp(self):
        p=pos("protect_profit")
        do_first_tp(p,"protect_profit")
        self.assertAlmostEqual(p["stop"],99.5)
        self.assertLess(p["stop"],p["entry_price"])
        self.assertGreater(p["stop"],p["initial_stop"])

    def test_rebuy_risk_guard_rejects_oversized_order(self):
        p=pos("rotate_support")
        do_first_tp(p,"rotate_support")
        p["remaining_rebuy"]=p["qty"]*40
        self.assertFalse(new.do_rebuy(p,101,7_200_000,.0006,
                                     "rotate_support",{"h4":[],"h4_closes":[]}))
        self.assertEqual(p["rotation_count"],0)

    def test_support_bounce_is_not_allowed_to_lower_sl_after_it_was_hit(self):
        p=pos("confirm_support")
        do_first_tp(p,"confirm_support")
        new.process_bar(p,bar(7_200_000,103,103,100,102.8),
                        "crypto","confirm_support",.0006,{})
        r=new.process_bar(p,bar(10_800_000,88,99,87,92),
                          "crypto","confirm_support",.0006,{})
        self.assertEqual(r["reason"],"GAP_STOP")
        self.assertEqual(r["rotations"],0)

    def test_runner_trail_uses_confirmed_ema_and_applies_next_bar(self):
        p=pos("trail_runner")
        do_first_tp(p,"trail_runner")
        with patch("arm_v1_swing_core.confirmed_h4",return_value={"ema20":103}):
            result=new.process_bar(p,bar(7_200_000,103,104,102,103),
                                   "crypto","trail_runner",.0006,{})
        self.assertIsNone(result)
        self.assertAlmostEqual(p["stop"],102)
        self.assertEqual(p["rotation_count"],0)
        result=new.process_bar(p,bar(10_800_000,103,103.5,101,102),
                               "crypto","trail_runner",.0006,{})
        self.assertEqual(result["reason"],"STOP")

    def test_no_same_bar_instant_rebuy_after_tp(self):
        p=pos("confirm_support")
        new.process_bar(p,bar(),"crypto","confirm_support",.0006,{},entry_bar=True)
        new.process_bar(p,bar(3_600_000,100,110,100,104),
                        "crypto","confirm_support",.0006,{})
        self.assertEqual(p["cycle_phase"],"WAIT_REBUY")
        self.assertEqual(p["rotation_count"],0)

if __name__=="__main__":unittest.main()
