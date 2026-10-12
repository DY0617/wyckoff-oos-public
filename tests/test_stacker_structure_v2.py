"""Offline tests: pivots confirmed, structural exits risk-capped, baseline parity."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

import agos_stacker_v1_core as v1
import stacker_structure_v2_core as v2


def structure():
    return {"pivot_low":[85,89,91],"pivot_high":[107,109,112],
            "ema20":103,"ema50":104,"structure_t":123}


class StructuralStopTests(unittest.TestCase):
    def test_baseline_exact_original_parameters(self):
        old=v1.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"stacker_regime")
        new=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"baseline")
        self.assertEqual(new["stop"],old["stop"])
        self.assertEqual(new["tp"],old["tp"])
        self.assertEqual(new["levels"],old["levels"])
        self.assertEqual(new["quantities"],old["quantities"])
        self.assertEqual(new["fees"],old["fees"])

    def test_confirmed_pivots_exclude_unconfirmed(self):
        candles=[{"h":101,"l":99,"ema20":102,"ema50":104,"ct":k*100} for k in range(15)]
        candles[7]={"h":110,"l":85,"ema20":102,"ema50":104,"ct":700}
        # Last unconfirmed bar (i-1) is extreme. Must NOT be seen as pivot.
        candles[11]={"h":130,"l":70,"ema20":102,"ema50":104,"ct":1100}
        a=v2.confirmed_structure(candles,12)
        self.assertIn(110,a["pivot_high"])
        self.assertIn(85,a["pivot_low"])
        self.assertNotIn(130,a["pivot_high"])
        self.assertNotIn(70,a["pivot_low"])
        self.assertEqual(a["structure_t"],1200)

    def test_long_sr_stop_is_beyond_all_adds(self):
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"sr_ema",structure())
        self.assertIsNotNone(p)
        self.assertEqual(p["stop_source"],"pivot")
        self.assertEqual(p["tp_source"],"ema20")
        self.assertGreater(p["tp"],p["avg"])
        self.assertLess(p["stop"],p["levels"][-1])
        self.assertEqual(p["tp"],103)
        planned=sum(q*(px-p["stop"]) for q,px in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(planned,150.000001)

    def test_short_sr_stop_and_resistance_tp(self):
        st={"pivot_low":[89,91,93],"pivot_high":[111,112,115],
            "ema20":97,"ema50":96,"structure_t":100}
        p=v2.entry_cycle("ETHUSDT","crypto","SHORT",100,2,0,20000,"sr_sr",st)
        self.assertIsNotNone(p)
        self.assertGreater(p["stop"],p["levels"][-1])
        self.assertLess(p["tp"],p["avg"])
        risk=sum(q*(p["stop"]-px) for q,px in zip(p["quantities"],p["levels"]))
        self.assertLessEqual(risk,150.00001)

    def test_skip_when_no_valid_stop(self):
        st={"pivot_low":[99,98],"pivot_high":[101,102],
            "ema20":103,"ema50":104,"structure_t":3}
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"sr_sr",st)
        self.assertIsNone(p)

    def test_skip_when_target_opposite_direction(self):
        st={"pivot_low":[85],"pivot_high":[99],
            "ema20":98,"ema50":98,"structure_t":3}
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"sr_ema",st)
        self.assertIsNone(p)

    def test_hybrid_ema_stop_if_valid_and_closer(self):
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"hybrid",structure())
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["stop"],92)
        self.assertEqual(p["stop_source"],"ema50_envelope")

    def test_target_remains_frozen_after_dca(self):
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"sr_ema",structure())
        tp=p["tp"]
        v2.additional_fill(p,98,3600000)
        self.assertEqual(p["tp"],tp)
        self.assertLess(p["avg"],100)
        self.assertGreater(p["tp"],p["avg"])

    def test_stop_first_after_adverse_adds(self):
        p=v2.entry_cycle("BTCUSDT","crypto","LONG",100,2,0,20000,"sr_ema",structure())
        bar={"o":100,"h":120,"l":84,"c":95,"t":0,"ct":3599999}
        fill=v2.apply_bar(p,bar,"crypto",is_entry_bar=True)
        self.assertEqual(fill,(p["stop"],"STOP"))
        self.assertEqual(len(p["fills"]),4)

    def test_short_target_ema(self):
        st={"pivot_low":[85],"pivot_high":[112],
            "ema20":97,"ema50":96,"structure_t":10}
        p=v2.entry_cycle("ETHUSDT","crypto","SHORT",100,2,0,20000,"sr_ema",st)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p["tp"],97)
        self.assertAlmostEqual(p["stop"],112.5)

if __name__=="__main__":
    unittest.main()
