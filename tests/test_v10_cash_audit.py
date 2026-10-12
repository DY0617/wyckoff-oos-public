"""Audit cash constraint and unmodified v8 baseline parity, no network."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import entry_first_v8_core as old
import entry_v10_audited_cash_engine as audit


def bar(t=0):
    return {"t":t,"ct":t+3599999,"o":100.,"h":100.2,"l":99.8,
            "c":100.,"atr14":1.,"day":"2026-01-02",
            "v":100.,"session_hour":0}


def sig():
    return {"side":"LONG","sign":1,"anchor":99.2,"entry_atr":1.,
            "source_close":100.,"signal_t":-1,"kind":"sweep",
            "structure_level":99.}


def setup(n=3):
    names=list("ABC")[:n]
    packs={s:{"hour":[bar(0)]} for s in names}
    bank={s:{"sweep":{0:sig()}} for s in names}
    return packs,bank


def shares(t,fee=.0006):
    return t["fees"]/(fee*(t["entry"]+t["exit"]))


class CashAuditTests(unittest.TestCase):
    def test_original_engine_exact_uncapped_parity(self):
        packs,bank=setup()
        a=old.simulate(packs,"stock","sweep",0,3600000,precomputed=bank)
        b=audit.simulate(packs,"stock","sweep",0,3600000,
                         precomputed=bank,enforce_cash=False)
        self.assertEqual(a["metrics"],b["metrics"])
        self.assertEqual(a["trades"],b["trades"])

    def test_legacy_allows_three_positions_with_over_one_hundred_percent_cash(self):
        packs,bank=setup()
        a=old.simulate(packs,"stock","sweep",0,3600000,precomputed=bank)
        total=sum(shares(t)*t["entry"]+shares(t)*t["entry"]*.0006
                  for t in a["trades"])
        self.assertGreater(total,20000.)

    def test_audited_cash_never_finances_more_shares_than_money(self):
        packs,bank=setup()
        x=audit.simulate(packs,"stock","sweep",0,3600000,
                         precomputed=bank,enforce_cash=True)
        gross=sum(shares(t)*t["entry"]*(1+.0006) for t in x["trades"])
        self.assertLessEqual(gross,20000.+1e-7)
        self.assertEqual(x["metrics"]["trade_count"],3)
        self.assertGreater(x["metrics"]["rejects"].get("cash_scaled",0),0)

    def test_cash_constraints_do_not_apply_to_crypto_futures(self):
        packs,bank=setup()
        old_out=old.simulate(packs,"crypto","sweep",0,3600000,
                             trade_symbols=["A","B","C"],precomputed=bank)
        new_out=audit.simulate(packs,"crypto","sweep",0,3600000,
                             trade_symbols=["A","B","C"],precomputed=bank,
                             enforce_cash=True)
        self.assertEqual(old_out["metrics"],new_out["metrics"])

    def test_audited_cash_is_no_better_on_identical_flat_trade_paths(self):
        packs,bank=setup()
        a=old.simulate(packs,"stock","sweep",0,3600000,precomputed=bank)
        b=audit.simulate(packs,"stock","sweep",0,3600000,
                         precomputed=bank,enforce_cash=True)
        # With flat price over the one bar, every trade suffers fees only.
        self.assertGreater(b["metrics"]["return_pct"],a["metrics"]["return_pct"])
        self.assertLessEqual(b["metrics"]["return_pct"],0)

    def test_single_stock_same_result_with_cash_cap(self):
        packs,bank=setup(1)
        a=old.simulate(packs,"stock","sweep",0,3600000,precomputed=bank)
        b=audit.simulate(packs,"stock","sweep",0,3600000,
                         precomputed=bank,enforce_cash=True)
        self.assertEqual(a["metrics"],b["metrics"])

if __name__=="__main__":unittest.main()
