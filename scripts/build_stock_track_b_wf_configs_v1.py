import itertools,json,os
from pathlib import Path

AXES=[
 ("rr_long_min",1.3),
 ("ema_gap_atr_max",1.5),
 ("trigger_window",12),
 ("test_spread_max",1.0),
 ("range_er_max",0.6),
]
out=[]
for bits in itertools.product((0,1),repeat=len(AXES)):
    ov={p:v for bit,(p,v) in zip(bits,AXES) if bit}
    name="cfg_"+"".join(map(str,bits))
    out.append({"name":name,"overrides":ov,"bits":list(bits)})
p=Path(os.environ.get("OUT","/tmp/stock_track_b_wf_configs_v1.json"))
p.write_text(json.dumps({"axes":[{"parameter":p,"preferred_value":v} for p,v in AXES],
                         "stage2_configs":out},indent=2),encoding="utf-8")
print("CONFIGS",len(out),str(p))
