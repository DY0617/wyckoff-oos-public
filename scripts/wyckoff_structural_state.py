class PersistentStructuralWyckoff:
    """
    Sequential Wyckoff structural engine.

    Key difference from snapshot scanning:
    - SC/BC -> AR -> ST is advanced only when each event becomes knowable.
    - Trading-range boundaries are frozen when Phase B first validates.
    - Spring/UTAD -> reclaim -> test is advanced sequentially on closed 4H bars.
    - Adverse structural invalidation resets the sequence instead of allowing an
      old range to be rediscovered later from a rolling window.
    - Phase D (SOS/SOW and LPS/LPSY) is tracked persistently for diagnostics.

    This is still an algorithmic formalization of Wyckoff, not discretionary
    chart reading.
    """

    def __init__(self, daily, h4, cfg, mode="v1"):
        self.d = daily
        self.h = h4
        self.cfg = dict(cfg)
        self.mode = mode
        self.di_done = -1
        self.hi_done = -1
        self.state = None
        self.last_event = None
        self.reset_count = 0

    @staticmethod
    def _med(xs):
        xs = sorted(xs)
        n = len(xs)
        if not n:
            return None
        return xs[n//2] if n % 2 else (xs[n//2-1] + xs[n//2]) / 2.0

    @staticmethod
    def _hp(b, j, upto):
        return j >= 1 and j + 1 <= upto and b[j]["h"] > b[j-1]["h"] and b[j]["h"] > b[j+1]["h"]

    @staticmethod
    def _lp(b, j, upto):
        return j >= 1 and j + 1 <= upto and b[j]["l"] < b[j-1]["l"] and b[j]["l"] < b[j+1]["l"]

    def _prior_bias(self, i):
        if i < 50:
            return None
        x = self.d[i]
        if not x.get("atr") or x.get("ema20") is None or x.get("ema50") is None:
            return None
        if self.d[i-10].get("ema20") is None:
            return None
        r = x["c"] / self.d[i-30]["c"] - 1.0
        slope = (x["ema20"] - self.d[i-10]["ema20"]) / (10.0 * x["atr"])
        acc = sum((r <= -0.08, x["c"] < x["ema20"] < x["ema50"], slope <= -0.10)) >= 2
        dist = sum((r >= 0.08, x["c"] > x["ema20"] > x["ema50"], slope >= 0.10)) >= 2
        if acc and not dist:
            return "ACC"
        if dist and not acc:
            return "DIST"
        return None

    def _climax(self, i):
        if i < 50:
            return None
        x = self.d[i]
        if not x.get("atr") or not x.get("ssma") or not x.get("vsma"):
            return None
        bias = self._prior_bias(i)
        if not bias:
            return None
        low20 = x["l"] <= min(z["l"] for z in self.d[i-19:i+1])
        high20 = x["h"] >= max(z["h"] for z in self.d[i-19:i+1])
        effort = (
            x["spread"] >= self.cfg["climax_spread_min"] * x["ssma"]
            and x["v"] >= self.cfg["climax_volume_min"] * x["vsma"]
        )
        if bias == "ACC" and low20 and effort and x["clv"] >= 0.35:
            return "ACC"
        if bias == "DIST" and high20 and effort and x["clv"] <= 0.65:
            return "DIST"
        return None

    def _start(self, bias, di):
        self.state = {
            "bias": bias,
            "phase": "A",
            "stage": "WAIT_AR",
            "sc": di,
            "ar": None,
            "st": None,
            "support": None,
            "resistance": None,
            "range_valid_di": None,
            "adverse_daily_out": 0,
            "spring": None,
            "reclaim": None,
            "test": None,
            "breakout": None,
            "breakout_confirmed": None,
            "breakout_origin_stage": None,
            "breakout_deadline": None,
            "breakout_outside_count": 0,
            "breakout_followthrough": False,
            "breakout_volume": None,
            "breakout_close": None,
            "lps": None,
            "setup_emitted": False,
            "emitted_keys": set(),
            "last_test": None,
            "c_test_count": 0,
            "lps_emitted": False,
            "invalid_reason": None,
        }
        self.last_event = {"type": "SC" if bias == "ACC" else "BC", "daily_i": di}

    def _reset(self, reason):
        if self.state is not None:
            self.state["invalid_reason"] = reason
        self.state = None
        self.last_event = {"type": "RESET", "reason": reason}
        self.reset_count += 1

    def _maybe_supersede_climax(self, di):
        bias = self._climax(di)
        if not bias:
            return False
        if self.state is None:
            self._start(bias, di)
            return True
        s = self.state
        # During preliminary Phase A, let a later, more extreme climax replace
        # the earlier candidate. This models identification of the terminal
        # climax without retrospectively rewriting an established range.
        if s["phase"] == "A":
            old = self.d[s["sc"]]
            new = self.d[di]
            more_extreme = (
                bias == "ACC" and new["l"] < old["l"]
            ) or (
                bias == "DIST" and new["h"] > old["h"]
            )
            if bias != s["bias"] or more_extreme:
                self._start(bias, di)
                return True
        return False

    def _boundaries(self, di):
        s = self.state
        sc, ar, st = s["sc"], s["ar"], s["st"]
        A = self.d[di].get("atr")
        if not A:
            return None
        if s["bias"] == "ACC":
            seed_s = min(self.d[sc]["l"], self.d[st]["l"])
            seed_r = self.d[ar]["h"]
        else:
            seed_s = self.d[ar]["l"]
            seed_r = max(self.d[sc]["h"], self.d[st]["h"])

        lows = [seed_s]
        highs = [seed_r]
        # Only confirmed pivots that are knowable by di are allowed.
        for j in range(max(1, sc), di):
            if self._lp(self.d, j, di) and abs(self.d[j]["l"] - seed_s) <= A:
                lows.append(self.d[j]["l"])
            if self._hp(self.d, j, di) and abs(self.d[j]["h"] - seed_r) <= A:
                highs.append(self.d[j]["h"])
        sup, res = self._med(lows), self._med(highs)
        if sup is None or res is None or sup >= res:
            return None
        window = self.d[sc:di+1]
        inside = sum(sup - A <= q["c"] <= res + A for q in window) / len(window)
        touches_s = sum(q["l"] <= sup + A for q in window)
        touches_r = sum(q["h"] >= res - A for q in window)
        age = di - sc
        internal = sum(
            1 for j in range(max(sc+1, 1), di)
            if self._lp(self.d, j, di) or self._hp(self.d, j, di)
        )
        valid = (
            18 <= age <= 105
            and res - sup >= 2.5 * A
            and inside >= 0.60
            and touches_s >= 2
            and touches_r >= 2
            and internal >= 2
            and di - ar >= 5
        )
        return sup, res, valid

    def _process_daily(self, di):
        if di < 0 or di >= len(self.d):
            return
        self._maybe_supersede_climax(di)
        s = self.state
        if s is None:
            return

        # Hard maximum age of one structural range.
        if di - s["sc"] > 105:
            self._reset("RANGE_AGE")
            self._maybe_supersede_climax(di)
            return
        s = self.state
        if s is None:
            return

        if s["stage"] == "WAIT_AR":
            # AR is a confirmed opposite pivot. Center j becomes known on di=j+1.
            j = di - 1
            if s["sc"] + 3 <= j <= s["sc"] + 15:
                if s["bias"] == "ACC" and self._hp(self.d, j, di):
                    move = self.d[j]["h"] - self.d[s["sc"]]["l"]
                    if move >= max(0.04 * self.d[s["sc"]]["c"], 1.5 * self.d[s["sc"]]["atr"]):
                        s["ar"] = j; s["stage"] = "WAIT_ST"
                        self.last_event = {"type": "AR", "daily_i": j}
                elif s["bias"] == "DIST" and self._lp(self.d, j, di):
                    move = self.d[s["sc"]]["h"] - self.d[j]["l"]
                    if move >= max(0.04 * self.d[s["sc"]]["c"], 1.5 * self.d[s["sc"]]["atr"]):
                        s["ar"] = j; s["stage"] = "WAIT_ST"
                        self.last_event = {"type": "AR", "daily_i": j}
            if s["stage"] == "WAIT_AR" and di > s["sc"] + 16:
                self._reset("NO_AR")
            return

        if s["stage"] == "WAIT_ST":
            ar = s["ar"]; q = self.d[di]; c = self.d[s["sc"]]
            if di > ar + 30:
                self._reset("NO_ST")
                return
            if di >= ar + 3 and q.get("atr"):
                if s["bias"] == "ACC":
                    near = q["l"] <= c["l"] + 1.1 * q["atr"]
                    beyond = q["c"] >= c["l"] - 0.4 * q["atr"]
                else:
                    near = q["h"] >= c["h"] - 1.1 * q["atr"]
                    beyond = q["c"] <= c["h"] + 0.4 * q["atr"]
                if near and beyond and q["v"] <= c["v"] and q["spread"] <= c["spread"]:
                    s["st"] = di
                    s["stage"] = "BUILD_RANGE"
                    self.last_event = {"type": "ST", "daily_i": di}
            return

        if s["stage"] == "BUILD_RANGE":
            b = self._boundaries(di)
            if b:
                sup, res, valid = b
                if valid:
                    # Freeze the trading-range boundaries at first Phase-B validation.
                    s["support"], s["resistance"] = sup, res
                    s["range_valid_di"] = di
                    s["phase"] = "B"
                    s["stage"] = "RANGE"
                    self.last_event = {"type": "PHASE_B", "daily_i": di, "support": sup, "resistance": res}
            return

        # Once Phase B is established, only adverse-side daily failure invalidates
        # the structure. Favorable-side strength is allowed to become SOS/SOW.
        if s["stage"] in ("RANGE", "PHASE_C", "PHASE_D"):
            q = self.d[di]; A = q.get("atr")
            if A and s["support"] is not None and s["resistance"] is not None:
                if s["bias"] == "ACC":
                    hard = q["c"] < s["support"] - 0.75 * A
                    adverse_out = q["c"] < s["support"]
                else:
                    hard = q["c"] > s["resistance"] + 0.75 * A
                    adverse_out = q["c"] > s["resistance"]
                s["adverse_daily_out"] = s["adverse_daily_out"] + 1 if adverse_out else 0
                if hard or s["adverse_daily_out"] >= 2:
                    self._reset("DAILY_RANGE_FAILURE")
                    return

    def _spring_penetration(self, hi):
        s = self.state; a = self.h[hi]; A = a.get("atr")
        if not A or not a.get("ssma") or not a.get("vsma"):
            return False
        pen = (s["support"] - a["l"]) if s["bias"] == "ACC" else (a["h"] - s["resistance"])
        return self.cfg["penetration_min"] * A <= pen <= self.cfg["penetration_max"] * A

    def _reclaimed(self, hi):
        s = self.state; a = self.h[hi]
        return a["c"] >= s["support"] if s["bias"] == "ACC" else a["c"] <= s["resistance"]

    def _test_ok(self, hi):
        s = self.state; q = self.h[hi]; a = self.h[s["spring"]["anchor"]]
        if not q.get("atr") or not q.get("ssma") or not q.get("vsma"):
            return False
        if s["bias"] == "ACC":
            return (
                q["l"] > a["l"]
                and q["l"] <= s["support"] + q["atr"]
                and q["spread"] <= self.cfg["test_spread_max"] * q["ssma"]
                and (
                    q["v"] <= self.cfg["test_volume_anchor_max"] * a["v"]
                    or q["v"] <= self.cfg["test_volume_sma_max"] * q["vsma"]
                )
                and q["clv"] >= 0.50
            )
        return (
            q["h"] < a["h"]
            and q["h"] >= s["resistance"] - q["atr"]
            and q["spread"] <= self.cfg["test_spread_max"] * q["ssma"]
            and (
                q["v"] <= self.cfg["test_volume_anchor_max"] * a["v"]
                or q["v"] <= self.cfg["test_volume_sma_max"] * q["vsma"]
            )
            and q["clv"] <= 0.50
        )

    def _setup_from_test(self, hi, source="PERSISTENT_WYCKOFF_C_TEST"):
        s = self.state
        q = self.h[hi]
        a = self.h[s["spring"]["anchor"]]
        if s["bias"] == "ACC":
            entry = q["h"] + self.cfg["entry_buffer_atr"] * q["atr"]
            stop = a["l"] - self.cfg["stop_buffer_atr"] * q["atr"]
            target = s["resistance"]
            rr = (target-entry)/(entry-stop) if entry > stop else -99
            direction = "LONG"
        else:
            entry = q["l"] - self.cfg["entry_buffer_atr"] * q["atr"]
            stop = a["h"] + self.cfg["stop_buffer_atr"] * q["atr"]
            target = s["support"]
            rr = (entry-target)/(stop-entry) if stop > entry else -99
            direction = "SHORT"
        if rr < self.cfg["rr_min"]:
            return None
        return {
            "bias": "ACCUMULATION" if s["bias"] == "ACC" else "DISTRIBUTION",
            "direction": direction,
            "phase": "C",
            "state": "PERSISTENT TEST",
            "support": s["support"],
            "resistance": s["resistance"],
            "sc_bc_open_ms": self.d[s["sc"]]["t"],
            "ar_open_ms": self.d[s["ar"]]["t"],
            "st_open_ms": self.d[s["st"]]["t"],
            "anchor_open_ms": self.h[s["spring"]["anchor"]]["t"],
            "reclaim_open_ms": self.h[s["reclaim"]]["t"],
            "test_open_ms": q["t"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr,
            "actionable": True,
            "source": source,
        }

    def _secondary_test_ok(self, hi):
        s = self.state
        if self.mode not in ("v2","v3","v4") or s is None or s["stage"] != "PHASE_C":
            return False
        prev_i = s.get("last_test")
        if prev_i is None or hi < prev_i + 2 or hi > prev_i + 24:
            return False
        q = self.h[hi]; prev = self.h[prev_i]
        if not q.get("atr") or not q.get("ssma") or not q.get("vsma"):
            return False
        if s["bias"] == "ACC":
            return (
                q["l"] > self.h[s["spring"]["anchor"]]["l"]
                and q["l"] >= prev["l"] - 0.15*q["atr"]
                and q["l"] <= s["support"] + q["atr"]
                and q["spread"] <= self.cfg["test_spread_max"] * q["ssma"]
                and q["v"] <= self.cfg["test_volume_sma_max"] * q["vsma"]
                and q["clv"] >= 0.50
            )
        return (
            q["h"] < self.h[s["spring"]["anchor"]]["h"]
            and q["h"] <= prev["h"] + 0.15*q["atr"]
            and q["h"] >= s["resistance"] - q["atr"]
            and q["spread"] <= self.cfg["test_spread_max"] * q["ssma"]
            and q["v"] <= self.cfg["test_volume_sma_max"] * q["vsma"]
            and q["clv"] <= 0.50
        )

    def _lps_ok(self, j, hi):
        s = self.state
        q = self.h[j]
        if not q.get("atr") or not q.get("ssma") or not q.get("vsma"):
            return False
        if s["bias"] == "ACC":
            return (
                self._lp(self.h, j, hi)
                and q["l"] >= s["resistance"] - 0.75*q["atr"]
                and q["c"] >= s["resistance"] - 0.25*q["atr"]
                and q["spread"] <= 1.10*q["ssma"]
                and q["v"] <= 1.00*q["vsma"]
            )
        return (
            self._hp(self.h, j, hi)
            and q["h"] <= s["support"] + 0.75*q["atr"]
            and q["c"] <= s["support"] + 0.25*q["atr"]
            and q["spread"] <= 1.10*q["ssma"]
            and q["v"] <= 1.00*q["vsma"]
        )

    def _v3_outside_close(self, hi):
        s = self.state; q = self.h[hi]; A = q.get("atr")
        if not A:
            return False
        if s["bias"] == "ACC":
            return q["c"] >= s["resistance"] + 0.10*A
        return q["c"] <= s["support"] - 0.10*A

    def _v3_deep_reentry(self, hi):
        s = self.state; q = self.h[hi]; A = q.get("atr")
        if not A:
            return False
        if s["bias"] == "ACC":
            return q["c"] < s["resistance"] - 0.15*A
        return q["c"] > s["support"] + 0.15*A

    def _v3_followthrough(self, hi):
        s = self.state; q = self.h[hi]; b = self.h[s["breakout"]]; A = q.get("atr")
        if not A:
            return False
        if s["bias"] == "ACC":
            return (
                self._v3_outside_close(hi)
                and (q["c"] >= s["breakout_close"] + 0.05*A or q["h"] >= b["h"] + 0.25*A)
            )
        return (
            self._v3_outside_close(hi)
            and (q["c"] <= s["breakout_close"] - 0.05*A or q["l"] <= b["l"] - 0.25*A)
        )

    def _lps_ok_v3(self, j, hi):
        s = self.state
        q = self.h[j]
        if not q.get("atr") or not q.get("ssma") or not q.get("vsma") or not s.get("breakout_volume"):
            return False
        base = s.get("breakout_confirmed")
        if base is None:
            return False
        # A valid backup must hold outside the old range after SOS/SOW confirmation.
        for k in range(base + 1, hi + 1):
            z = self.h[k]; A = z.get("atr")
            if not A:
                return False
            if s["bias"] == "ACC" and z["c"] < s["resistance"] - 0.10*A:
                return False
            if s["bias"] == "DIST" and z["c"] > s["support"] + 0.10*A:
                return False
        if s["bias"] == "ACC":
            return (
                self._lp(self.h, j, hi)
                and q["l"] >= s["resistance"] - 0.15*q["atr"]
                and q["l"] <= s["resistance"] + 1.25*q["atr"]
                and q["c"] >= s["resistance"]
                and q["spread"] <= 0.90*q["ssma"]
                and q["v"] <= 0.85*q["vsma"]
                and q["v"] <= 0.90*s["breakout_volume"]
                and q["clv"] >= 0.45
            )
        return (
            self._hp(self.h, j, hi)
            and q["h"] <= s["support"] + 0.15*q["atr"]
            and q["h"] >= s["support"] - 1.25*q["atr"]
            and q["c"] <= s["support"]
            and q["spread"] <= 0.90*q["ssma"]
            and q["v"] <= 0.85*q["vsma"]
            and q["v"] <= 0.90*s["breakout_volume"]
            and q["clv"] <= 0.55
        )

    def _setup_from_lps(self, j, hi):
        s = self.state
        p = self.h[j]; confirm = self.h[hi]
        A = confirm.get("atr")
        if not A:
            return None
        height = s["resistance"] - s["support"]
        if height <= 0:
            return None
        if s["bias"] == "ACC":
            entry = max(p["h"], confirm["h"]) + self.cfg["entry_buffer_atr"]*A
            stop = p["l"] - self.cfg["stop_buffer_atr"]*A
            target = s["resistance"] + height
            rr = (target-entry)/(entry-stop) if entry > stop else -99
            direction = "LONG"
        else:
            entry = min(p["l"], confirm["l"]) - self.cfg["entry_buffer_atr"]*A
            stop = p["h"] + self.cfg["stop_buffer_atr"]*A
            target = s["support"] - height
            rr = (entry-target)/(stop-entry) if stop > entry else -99
            direction = "SHORT"
        if rr < self.cfg["rr_min"]:
            return None
        return {
            "bias": "ACCUMULATION" if s["bias"] == "ACC" else "DISTRIBUTION",
            "direction": direction,
            "phase": "D",
            "state": "PERSISTENT LPS" if s["bias"] == "ACC" else "PERSISTENT LPSY",
            "support": s["support"],
            "resistance": s["resistance"],
            "sc_bc_open_ms": self.d[s["sc"]]["t"],
            "ar_open_ms": self.d[s["ar"]]["t"],
            "st_open_ms": self.d[s["st"]]["t"],
            "breakout_open_ms": self.h[s["breakout"]]["t"],
            "lps_lpsy_open_ms": p["t"],
            "test_open_ms": p["t"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr,
            "actionable": True,
            "source": "PERSISTENT_WYCKOFF_D_LPS" if s["bias"] == "ACC" else "PERSISTENT_WYCKOFF_D_LPSY",
        }

    def _favorable_breakout(self, hi):
        s = self.state; a = self.h[hi]; A = a.get("atr")
        if not A or not a.get("ssma") or not a.get("vsma"):
            return False
        if self.mode in ("v3","v4"):
            if s["bias"] == "ACC":
                return (
                    a["c"] >= s["resistance"] + 0.35*A
                    and a["spread"] >= 1.30*a["ssma"]
                    and a["v"] >= 1.20*a["vsma"]
                    and a["clv"] >= 0.65
                )
            return (
                a["c"] <= s["support"] - 0.35*A
                and a["spread"] >= 1.30*a["ssma"]
                and a["v"] >= 1.20*a["vsma"]
                and a["clv"] <= 0.35
            )
        if s["bias"] == "ACC":
            return (
                a["c"] >= s["resistance"] + 0.25*A
                and a["spread"] >= 1.3*a["ssma"]
                and a["v"] >= 1.2*a["vsma"]
            )
        return (
            a["c"] <= s["support"] - 0.25*A
            and a["spread"] >= 1.3*a["ssma"]
            and a["v"] >= 1.2*a["vsma"]
        )

    def _process_h4(self, hi):
        s = self.state
        if s is None or s["stage"] not in ("RANGE", "PHASE_C", "PHASE_D_PENDING", "PHASE_D"):
            return None
        # Never use 4H bars from before Phase B was actually confirmed.
        if s["range_valid_di"] is None:
            return None
        setup = None

        if s["stage"] in ("RANGE", "PHASE_C") and self._favorable_breakout(hi):
            if self.mode in ("v3","v4"):
                s["breakout_origin_stage"] = s["stage"]
                s["stage"] = "PHASE_D_PENDING"
                s["breakout"] = hi
                s["breakout_confirmed"] = None
                s["breakout_deadline"] = hi + 3
                s["breakout_outside_count"] = 1
                s["breakout_followthrough"] = False
                s["breakout_volume"] = self.h[hi]["v"]
                s["breakout_close"] = self.h[hi]["c"]
                self.last_event = {"type": "SOS_CANDIDATE" if s["bias"] == "ACC" else "SOW_CANDIDATE", "h4_i": hi}
            else:
                s["phase"] = "D"; s["stage"] = "PHASE_D"; s["breakout"] = hi
                self.last_event = {"type": "SOS" if s["bias"] == "ACC" else "SOW", "h4_i": hi}
            return None

        if s["stage"] == "PHASE_D_PENDING" and self.mode in ("v3","v4"):
            if hi <= s["breakout"]:
                return None
            if self._v3_deep_reentry(hi):
                origin = s.get("breakout_origin_stage") or "RANGE"
                s["stage"] = origin
                s["breakout"] = None
                s["breakout_confirmed"] = None
                s["breakout_deadline"] = None
                s["breakout_outside_count"] = 0
                s["breakout_followthrough"] = False
                s["breakout_volume"] = None
                s["breakout_close"] = None
                self.last_event = {"type": "FALSE_BREAKOUT_RETURN", "h4_i": hi}
                return None
            if hi <= s["breakout_deadline"]:
                if self._v3_outside_close(hi):
                    s["breakout_outside_count"] += 1
                if self._v3_followthrough(hi):
                    s["breakout_followthrough"] = True
                if s["breakout_outside_count"] >= 2 and s["breakout_followthrough"]:
                    s["phase"] = "D"
                    s["stage"] = "PHASE_D"
                    s["breakout_confirmed"] = hi
                    self.last_event = {"type": "SOS_CONFIRMED" if s["bias"] == "ACC" else "SOW_CONFIRMED", "h4_i": hi}
                return None
            origin = s.get("breakout_origin_stage") or "RANGE"
            s["stage"] = origin
            s["breakout"] = None
            s["breakout_confirmed"] = None
            s["breakout_deadline"] = None
            s["breakout_outside_count"] = 0
            s["breakout_followthrough"] = False
            s["breakout_volume"] = None
            s["breakout_close"] = None
            self.last_event = {"type": "NO_FOLLOWTHROUGH_RETURN", "h4_i": hi}
            return None

        if s["stage"] == "RANGE":
            sp = s["spring"]
            if sp is None and self._spring_penetration(hi):
                s["spring"] = {"start": hi, "anchor": hi, "deadline": hi+2, "reclaimed": False}
                self.last_event = {"type": "SPRING" if s["bias"] == "ACC" else "UTAD", "h4_i": hi}
                sp = s["spring"]
            if sp is not None and not sp["reclaimed"]:
                if hi <= sp["deadline"]:
                    if s["bias"] == "ACC" and self.h[hi]["l"] < self.h[sp["anchor"]]["l"]:
                        sp["anchor"] = hi
                    if s["bias"] == "DIST" and self.h[hi]["h"] > self.h[sp["anchor"]]["h"]:
                        sp["anchor"] = hi
                    if self._reclaimed(hi):
                        sp["reclaimed"] = True
                        s["reclaim"] = hi
                        self.last_event = {"type": "RECLAIM", "h4_i": hi}
                if not sp["reclaimed"] and hi > sp["deadline"]:
                    s["spring"] = None
                    self.last_event = {"type": "SPRING_FAIL", "h4_i": hi}
                    return None

            sp = s["spring"]
            if sp is not None and sp["reclaimed"]:
                r = s["reclaim"]
                if r + 1 <= hi <= r + 8 and self._test_ok(hi):
                    s["test"] = hi
                    s["last_test"] = hi
                    s["c_test_count"] = 1
                    s["phase"] = "C"; s["stage"] = "PHASE_C"
                    self.last_event = {"type": "TEST", "h4_i": hi}
                    if not s["setup_emitted"]:
                        setup = self._setup_from_test(hi)
                        s["setup_emitted"] = True
                        s["emitted_keys"].add(("C", hi))
                    return setup
                if hi > r + 8:
                    # Failed test cycle; return to Phase B and wait for a new spring/UTAD.
                    s["spring"] = None; s["reclaim"] = None
                    self.last_event = {"type": "NO_TEST_RESET_TO_B", "h4_i": hi}

        if s["stage"] == "PHASE_C" and self.mode in ("v2","v3","v4"):
            if s.get("c_test_count", 0) < 2 and self._secondary_test_ok(hi):
                s["last_test"] = hi
                s["c_test_count"] = s.get("c_test_count", 0) + 1
                self.last_event = {"type": "SECONDARY_TEST", "h4_i": hi}
                key = ("C2", hi)
                if key not in s["emitted_keys"]:
                    setup = self._setup_from_test(hi, source="PERSISTENT_WYCKOFF_C_SECONDARY_TEST")
                    s["emitted_keys"].add(key)
                    if setup is not None:
                        return setup

        if s["stage"] == "PHASE_D" and s["breakout"] is not None:
            # Confirm LPS/LPSY sequentially (center hi-1 is known only after hi closes).
            j = hi - 1
            base = s.get("breakout_confirmed") if self.mode in ("v3","v4") else s["breakout"]
            max_wait = 14 if self.mode in ("v3","v4") else 12
            if base is not None and base + 2 <= j <= base + max_wait:
                if self.mode in ("v3","v4"):
                    valid_lps = self._lps_ok_v3(j, hi)
                elif self.mode == "v2":
                    valid_lps = self._lps_ok(j, hi)
                else:
                    valid_lps = (
                        s["bias"] == "ACC" and self._lp(self.h, j, hi)
                        and self.h[j]["l"] >= s["resistance"] - self.h[j]["atr"]
                    ) or (
                        s["bias"] == "DIST" and self._hp(self.h, j, hi)
                        and self.h[j]["h"] <= s["support"] + self.h[j]["atr"]
                    )
                if valid_lps:
                    s["lps"] = j
                    self.last_event = {"type": "LPS" if s["bias"] == "ACC" else "LPSY", "h4_i": j}
                    # v4 keeps Phase-D/LPS state for context only; it does not
                    # emit Phase-D trade entries. v2/v3 retain their historical behavior.
                    if self.mode in ("v2","v3") and not s["lps_emitted"]:
                        s["lps_emitted"] = True
                        setup = self._setup_from_lps(j, hi)
                        if setup is not None:
                            if self.mode == "v3":
                                setup["source"] = "PERSISTENT_WYCKOFF_D_CONFIRMED_LPS" if s["bias"] == "ACC" else "PERSISTENT_WYCKOFF_D_CONFIRMED_LPSY"
                                setup["breakout_confirmed_open_ms"] = self.h[s["breakout_confirmed"]]["t"]
                            return setup
        return setup

    def snapshot(self):
        s = self.state
        if s is None:
            return {
                "bias": "NONE", "phase": "NONE", "state": "NO ACTIVE STRUCTURE",
                "support": None, "resistance": None, "actionable": False,
                "persistent": True, "reset_count": self.reset_count,
            }
        return {
            "bias": "ACCUMULATION" if s["bias"] == "ACC" else "DISTRIBUTION",
            "phase": s["phase"],
            "state": s["stage"],
            "support": s["support"],
            "resistance": s["resistance"],
            "actionable": False,
            "sc_bc_open_ms": self.d[s["sc"]]["t"],
            "ar_open_ms": self.d[s["ar"]]["t"] if s["ar"] is not None else None,
            "st_open_ms": self.d[s["st"]]["t"] if s["st"] is not None else None,
            "breakout_open_ms": self.h[s["breakout"]]["t"] if s["breakout"] is not None else None,
            "lps_lpsy_open_ms": self.h[s["lps"]]["t"] if s["lps"] is not None else None,
            "persistent": True,
            "reset_count": self.reset_count,
        }

    def update(self, di, hi):
        # Advance daily state only as daily bars actually become closed/known.
        for k in range(self.di_done + 1, di + 1):
            self._process_daily(k)
        self.di_done = max(self.di_done, di)

        emitted = None
        for k in range(self.hi_done + 1, hi + 1):
            z = self._process_h4(k)
            if z is not None:
                emitted = z
        self.hi_done = max(self.hi_done, hi)

        return emitted if emitted is not None else self.snapshot()
