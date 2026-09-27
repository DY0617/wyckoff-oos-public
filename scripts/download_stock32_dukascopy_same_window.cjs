const fs = require("fs");
const path = require("path");
const { getHistoricalRates } = require("dukascopy-node");

const baseline = JSON.parse(fs.readFileSync("data/validation/stock53_rth_entry_timing_abc.json","utf8"));
const MAP = {
  AAPL:"aaplususd", AMZN:"amznususd", AVGO:"avgoususd", DELL:"dellususd",
  MSFT:"msftususd", MU:"muususd", AMD:"amdususd", BABA:"babaususd",
  INTC:"intcususd", JPM:"jpmususd", NFLX:"nflxususd", V:"vususd",
  COST:"costususd", GOOGL:"googlususd", LLY:"llyususd", META:"fbususd",
  NVDA:"nvdaususd", QQQ:"qqqususd", TSLA:"tslaususd", UBER:"uberususd",
  WMT:"wmtususd", AMAT:"amatususd", CAT:"catususd", HD:"hdususd",
  MRVL:"mrvlususd", ORCL:"orclususd", SPY:"spyususd", TSM:"tsmususd",
  CRM:"crmususd", CSCO:"cscoususd", DIS:"disususd", IBM:"ibmususd"
};
const outDir = "data/validation/dukascopy_same_window_raw";
fs.mkdirSync(outDir,{recursive:true});
const from = new Date("2026-01-01T00:00:00Z");
const to = new Date(baseline.generated_at);
const entries = Object.entries(MAP);
const manifest = {generated_at:new Date().toISOString(), from:from.toISOString(), to:to.toISOString(), provider:"Dukascopy", price_type:"bid", timeframe:"m15", symbols:{}, errors:{}};

async function one(symbol,instrument){
  const data = await getHistoricalRates({
    instrument,
    dates:{from,to},
    timeframe:"m15",
    format:"json",
    priceType:"bid",
    volumes:true,
    batchSize:12,
    pauseBetweenBatchesMs:25
  });
  const rows = Array.isArray(data) ? data : [];
  fs.writeFileSync(path.join(outDir, symbol+".json"), JSON.stringify(rows));
  manifest.symbols[symbol] = {instrument, rows:rows.length, first:rows[0]?.timestamp ?? null, last:rows.at(-1)?.timestamp ?? null};
  console.log("DOWNLOADED",symbol,instrument,rows.length);
}
async function main(){
  for(let i=0;i<entries.length;i+=4){
    const batch=entries.slice(i,i+4);
    const rs=await Promise.allSettled(batch.map(([s,inst])=>one(s,inst)));
    rs.forEach((r,idx)=>{ if(r.status==="rejected"){ const [s,inst]=batch[idx]; manifest.errors[s]=String(r.reason?.stack||r.reason); console.error("ERROR",s,inst,manifest.errors[s]); }});
  }
  fs.writeFileSync(path.join(outDir,"manifest.json"), JSON.stringify(manifest,null,2));
  console.log("MANIFEST",JSON.stringify(manifest));
}
main().catch(e=>{console.error(e);process.exit(1)});