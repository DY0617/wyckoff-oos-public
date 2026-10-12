"""Unit tests for causal Stacker v3 rotation, risk and stop lowering."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

import stacker_rotation_v3_core as v3


def sig():
    return {"side":"LONG","atr":2.0,"signal_t":0,
            "structure":{"pivot_low":[91.],"pivot_high":[109.],
                         "ema20":103.0,"ema50":105.0,"structure_t":-1}}


def bar(o=100,h=101,l=99,c=100,t=0):
    return {"o":o,"h":h,"l":l,"c":c,"t":t,"ct":t+3600000-1,
            "day":"2025-01-01"}


def pos(mode="rotate_lower"):
    p=v3.position_from_signal("BTCUSDT","crypto",sig(),100,0,20000,0.0006)
    assert p is not None
    p["mode"]=mode
    return p


class RotationTests(unittest.TestCase):
    def test_first_position_limits(self):
        p=pos()
        self.assertEqual(p["tp"],103.0)
        self.assertEqual(p["stop"],90.5)
        self.assertLessEqual(sum(q*x for q,x in zip(p["quantities"],p["levels"])),14000.001)
        all_stop=sum(q*(x-p["stop"]+0.001*(x+p["stop"]))
                     for q,x in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(all_stop,p["max_risk_budget"]+1e-6)

    def test_static_full_exit(self):
        p=pos("static")
        self.assertIsNone(v3.process_bar(p,bar(h=104,l=99,c=103),"crypto","static",.0006,{},True))
        completed=v3.process_bar(p,bar(o=101,h=104,l=99,c=103,t=3600000),
                                 "crypto","static",.0006,{})
        self.assertIsNotNone(completed)
        self.assertEqual(completed["reason"],"TP_FULL")
        self.assertEqual(completed["rotations"],0)

    def test_partial_then_risk_funded_lower_stop(self):
        p=pos()
        self.assertIsNone(v3.process_bar(p,bar(),"crypto","rotate_lower",.0006,{},True))
        self.assertIsNone(v3.process_bar(p,bar(o=100,h=104,l=99,c=103,t=3600000),
                                       "crypto","rotate_lower",.0006,{}))
        self.assertEqual(p["cycle_phase"],"WAIT_REBUY")
        self.assertAlmostEqual(p["rebuy_level"],101.0)
        self.assertAlmostEqual(p["qty"],p["quantities"][0]*0.50)
        pack={"h4":[],"h4_closes":[]}
        self.assertIsNone(v3.process_bar(p,bar(o=103,h=104,l=100,c=101,t=7200000),
                                        "crypto","rotate_lower",.0006,pack))
        self.assertEqual(p["rotation_count"],1)
        self.assertEqual(p["sl_moves"],1)
        self.assertAlmostEqual(p["stop"],90.0)
        self.assertAlmostEqual(p["avg"],100.5)
        self.assertGreaterEqual(v3.projected_floor(p,p["stop"]),-p["max_risk_budget"]-1e-6)

    def test_stop_priority_prevents_retroactive_widening(self):
        p=pos()
        v3.process_bar(p,bar(),"crypto","rotate_lower",.0006,{},True)
        v3.process_bar(p,bar(o=100,h=104,l=99,c=103,t=3600000),
                       "crypto","rotate_lower",.0006,{})
        pack={"h4":[],"h4_closes":[]}
        completed=v3.process_bar(p,bar(o=103,h=107,l=89,c=100,t=7200000),
                                 "crypto","rotate_lower",.0006,pack)
        self.assertEqual(completed["reason"],"STOP")
        self.assertEqual(completed["rotations"],0)
        self.assertEqual(completed["last_stop"],90.5)

    def test_unfunded_stop_lowering_is_rejected(self):
        p=pos()
        p["cycle_phase"]="WAIT_REBUY"
        p["remaining_rebuy"]=p["qty"]*20
        p["gross_realized"]=0
        self.assertIsNone(v3.planned_rebuy(p,"rotate_lower",101,.0006))

    def test_support_roll_requires_confirmed_lower_pivot(self):
        p=pos()
        p["cycle_phase"]="WAIT_REBUY"
        p["remaining_rebuy"]=p["qty"]*0.5
        p["gross_realized"]=100
        upper={"pivot_low":[92,94],"pivot_high":[110],"ema20":103,"ema50":105}
        self.assertIsNone(v3.planned_rebuy(p,"rotate_support",101,.0006,upper))
        lower={"pivot_low":[88,89],"pivot_high":[110],"ema20":103,"ema50":105}
        candidate=v3.planned_rebuy(p,"rotate_support",101,.0006,lower)
        self.assertIsNotNone(candidate)
        self.assertLess(candidate,p["stop"])

    def test_accounting_full_partial_round_trip(self):
        p=pos()
        initial_qty=p["qty"]
        v3.realize(p,initial_qty*.5,103,.0006)
        self.assertAlmostEqual(p["qty"],initial_qty*.5)
        final=v3.finish(p,100,7200000,"END_OF_DATA",.0006)
        expected=initial_qty*.5*3-initial_qty*100*.0006-(initial_qty*.5*103+initial_qty*.5*100)*.0006
        self.assertAlmostEqual(final["pnl"],expected,places=6)

    def test_no_add_and_tp_same_bar(self):
        p=pos("rotate_lower")
        r=v3.process_bar(p,bar(o=100,h=105,l=97,c=103),"crypto",
                         "rotate_lower",.0006,{},True)
        self.assertIsNone(r)
        self.assertEqual(p["cycle_phase"],"LADDER")
        self.assertEqual(len(p["fills"]),2)

    def test_runner_exit_if_no_rebuy(self):
        p=pos()
        v3.process_bar(p,bar(),"crypto","rotate_lower",.0006,{},True)
        v3.process_bar(p,bar(o=100,h=104,l=99,c=103,t=3600000),
                       "crypto","rotate_lower",.0006,{})
        r=v3.process_bar(p,bar(o=104,h=107,l=102,c=106,t=7200000),
                         "crypto","rotate_lower",.0006,{})
        self.assertEqual(r["reason"],"RUNNER_TP")
        self.assertEqual(r["rotations"],0)

if __name__=="__main__":
    unittest.main()
