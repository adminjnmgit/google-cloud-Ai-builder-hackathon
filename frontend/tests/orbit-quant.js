/*
 * Orbit Quant Engine: event to EBITDA, with scenario bands, materiality, calibrated confidence and a decision layer.
 * Runs in Node (tests, CLI) and in the browser (window.OrbitQuant). No dependencies.
 *
 * Pipeline per (event, company):
 *   verify sources -> map channels (first order, plus second order through event links) -> shock distribution
 *   -> Monte Carlo transmission -> scenario bands -> materiality -> confidence (components, isotonic calibration)
 *   -> levers and decision -> audit trace
 *
 * Units: EBITDA impact is in percent of EBITDA. Variable moves are in the event's unit (%, bps or pts).
 * A channel's beta is the median EBITDA % change per 1 unit of the variable (per 100 bps for rate-type variables)
 * before pass-through, hedge and substitution. sigmaC is the lognormal uncertainty on beta.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(); else root.OrbitQuant = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ------------------------------------------------------------------ numerics
  function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function gaussians(rng, n) { const out = new Float64Array(n); for (let i = 0; i < n; i += 2) { let u = 0, v = 0; while (u === 0) u = rng(); while (v === 0) v = rng(); const r = Math.sqrt(-2 * Math.log(u)), t = 2 * Math.PI * v; out[i] = r * Math.cos(t); if (i + 1 < n) out[i + 1] = r * Math.sin(t); } return out; }
  // Acklam's inverse normal CDF
  function qnorm(p) { const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00], b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01], c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00], d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]; const pl = 0.02425, ph = 1 - pl; let q, r; if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); } if (p <= ph) { q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); } q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  function quantile(sorted, p) { const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo); }
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const r1 = x => Math.round(x * 10) / 10, r2 = x => Math.round(x * 100) / 100, r3 = x => Math.round(x * 1000) / 1000;

  // Pool-adjacent-violators isotonic regression: returns a monotone step map raw -> calibrated
  function isotonic(pairs) {
    const pts = pairs.slice().sort((a, b) => a[0] - b[0]);
    const blocks = pts.map(p => ({ sum: p[1], n: 1, lo: p[0], hi: p[0] }));
    let i = 0;
    while (i < blocks.length - 1) {
      if (blocks[i].sum / blocks[i].n > blocks[i + 1].sum / blocks[i + 1].n) {
        const m = { sum: blocks[i].sum + blocks[i + 1].sum, n: blocks[i].n + blocks[i + 1].n, lo: blocks[i].lo, hi: blocks[i + 1].hi };
        blocks.splice(i, 2, m); if (i > 0) i--;
      } else i++;
    }
    const steps = blocks.map(b => ({ x: (b.lo + b.hi) / 2, y: b.sum / b.n, lo: b.lo, hi: b.hi, n: b.n }));
    const predict = x => { if (!steps.length) return x; if (x <= steps[0].x) return steps[0].y; if (x >= steps[steps.length - 1].x) return steps[steps.length - 1].y; for (let k = 0; k < steps.length - 1; k++) { const a = steps[k], b = steps[k + 1]; if (x >= a.x && x <= b.x) return a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x || 1); } return x; };
    return { steps, predict };
  }

  // Platt scaling: logistic fit of hit ~ a + b * logit(raw) by Newton's method. Smooth and monotone; used for the live score. Isotonic bins stay as the diagnostic.
  function platt(pairs) {
    const logit = p => Math.log(clamp(p, 1e-4, 1 - 1e-4) / (1 - clamp(p, 1e-4, 1 - 1e-4))), sig = z => 1 / (1 + Math.exp(-z));
    let a = 0, b = 1;
    for (let it = 0; it < 25; it++) {
      let g0 = 0, g1 = 0, h00 = 0, h01 = 0, h11 = 0;
      pairs.forEach(([x, y]) => { const z = logit(x), p = sig(a + b * z), w = p * (1 - p); g0 += p - y; g1 += (p - y) * z; h00 += w; h01 += w * z; h11 += w * z * z; });
      h00 += 1e-3; h11 += 1e-3; // ridge
      const det = h00 * h11 - h01 * h01; if (Math.abs(det) < 1e-12) break;
      const da = (h11 * g0 - h01 * g1) / det, db = (h00 * g1 - h01 * g0) / det; a -= da; b -= db; if (Math.abs(da) + Math.abs(db) < 1e-9) break;
    }
    return { a: r3(a), b: r3(b), predict: x => sig(a + b * logit(x)) };
  }

  // ------------------------------------------------------------------ data: tags, events, companies
  const TAGS = ['Supply disruption', 'Commodity shock', 'Geopolitical event', 'Interest-rate change', 'Trade restriction', 'Regulation', 'Demand shock', 'Technology change'];

  // sigmaE: lognormal dispersion of the realised move around the stated magnitude. hit: precedent direction hit rate for this event type.
  const EVENTS = [
    { id: 'crude', title: 'Crude oil rises 10% following a supply disruption', keys: ['crude', 'oil', 'brent', 'supply'], tags: ['Supply disruption', 'Commodity shock', 'Geopolitical event'], date: '2026-10-03', horizonQ: 2, horizonText: '1 to 3 quarters',
      variable: { name: 'crude', label: 'Crude oil price', unit: '%', magnitude: 10 }, sigmaE: 0.25, hit: 0.70,
      precedents: [{ title: '2022 supply shock', sim: 0.82, outcome: 'Airline EBITDA fell 4 to 6%; upstream EBITDA rose 5 to 8%' }, { title: '2019 Abqaiq attack', sim: 0.66, outcome: 'Crude +15% for three weeks, then normalised' }],
      sources: [{ src: 'Exchange settlement (Brent)', cred: 0.99, type: 'FACT', claim: 'move' }, { src: 'Wire service', cred: 0.92, type: 'FACT', claim: 'outage' }, { src: 'OMC price notice', cred: 0.9, type: 'FACT', claim: 'retail' }, { src: 'Transport association', cred: 0.65, type: 'CLAIM', claim: 'freight' }, { src: 'Analyst note', cred: 0.6, type: 'PREDICTION', claim: 'polymer' }] },
    { id: 'rate', title: 'The policy rate rises by 50 basis points', keys: ['rate', 'repo', 'policy', 'interest', 'mpc'], tags: ['Interest-rate change'], date: '2026-10-09', horizonQ: 2, horizonText: '1 to 2 quarters',
      variable: { name: 'rate', label: 'Policy rate', unit: 'bps', magnitude: 50 }, sigmaE: 0.20, hit: 0.72,
      precedents: [{ title: '2022 to 2023 hiking cycle', sim: 0.88, outcome: 'Private bank NIM widened 20 to 35 bps; auto volume growth slowed' }],
      sources: [{ src: 'Central bank statement', cred: 0.99, type: 'FACT', claim: 'hike' }, { src: 'Wire service', cred: 0.95, type: 'FACT', claim: 'hike' }, { src: 'Bank circular', cred: 0.9, type: 'FACT', claim: 'reset' }, { src: 'Columnist', cred: 0.5, type: 'INTERPRETATION', claim: 'stance' }] },
    { id: 'steel', title: 'Steel prices rise 12% in a commodity shock', keys: ['steel', 'hrc', 'commodity', 'metal'], tags: ['Commodity shock'], date: '2026-10-07', horizonQ: 2, horizonText: '1 to 3 quarters',
      variable: { name: 'steel', label: 'Steel price', unit: '%', magnitude: 12 }, sigmaE: 0.30, hit: 0.70,
      precedents: [{ title: '2021 steel rally', sim: 0.8, outcome: 'Auto OEM margins fell 100 to 250 bps; metal producers gained' }, { title: '2016 minimum import price', sim: 0.72, outcome: 'Domestic steel +9% for two quarters' }],
      sources: [{ src: 'Exchange data (HRC)', cred: 0.97, type: 'FACT', claim: 'move' }, { src: 'Mill price circular', cred: 0.9, type: 'FACT', claim: 'move' }, { src: 'Trade daily', cred: 0.7, type: 'CLAIM', claim: 'further' }, { src: 'Regional newspaper', cred: 0.55, type: 'CLAIM', claim: 'move', conflict: true }] },
    { id: 'pharma', title: 'A trade restriction cuts a key drug intermediate by 15%', keys: ['pharma', 'drug', 'intermediate', 'api', 'trade'], tags: ['Trade restriction'], date: '2026-10-01', horizonQ: 2, horizonText: '1 to 3 quarters',
      variable: { name: 'intermediate', label: 'Drug intermediate price', unit: '%', magnitude: 15 }, sigmaE: 0.35, hit: 0.68,
      precedents: [{ title: '2020 API supply squeeze', sim: 0.78, outcome: 'Formulation makers lost 150 to 300 bps of margin; domestic API makers gained' }],
      sources: [{ src: 'Customs notification', cred: 0.96, type: 'FACT', claim: 'restriction' }, { src: 'Wire service', cred: 0.92, type: 'FACT', claim: 'restriction' }, { src: 'Importer association', cred: 0.68, type: 'CLAIM', claim: 'quotes' }, { src: 'Broker note', cred: 0.6, type: 'PREDICTION', claim: 'duration' }] },
    { id: 'regulation', title: 'A regulation cuts essential drug prices by 8%', keys: ['regulation', 'price control', 'nppa', 'essential', 'drug prices'], tags: ['Regulation'], date: '2026-10-05', horizonQ: 2, horizonText: '1 to 2 quarters',
      variable: { name: 'drug_price', label: 'Essential drug prices', unit: '%', magnitude: -8 }, sigmaE: 0.20, hit: 0.74,
      precedents: [{ title: '2013 drug price control order', sim: 0.8, outcome: 'Affected portfolios lost 2 to 4% of EBITDA over two quarters' }],
      sources: [{ src: 'Gazette notification', cred: 0.98, type: 'FACT', claim: 'cut' }, { src: 'PIB release', cred: 0.95, type: 'FACT', claim: 'cut' }, { src: 'Industry body', cred: 0.65, type: 'CLAIM', claim: 'impact' }],
      secondOrder: [{ variable: 'bond_yield', label: 'Government bond yields', unit: 'bps', magnitude: -8, sigma: 0.60, hit: 0.55, path: ['Essential drug prices -8%', 'CPI about -0.08 pp', 'Bond yields about -8 bps'] }] },
    { id: 'demand', title: 'Enterprise technology budgets fall 8%', keys: ['demand', 'technology budgets', 'it spend', 'enterprise', 'tech'], tags: ['Demand shock'], date: '2026-10-02', horizonQ: 2, horizonText: '1 to 3 quarters',
      variable: { name: 'tech_budget', label: 'Enterprise technology budgets', unit: '%', magnitude: -8 }, sigmaE: 0.35, hit: 0.66,
      precedents: [{ title: '2009 and 2023 IT spending cuts', sim: 0.74, outcome: 'Indian IT services EBITDA fell 2 to 4% with a two-quarter lag' }],
      sources: [{ src: 'Industry survey (n=400 CIOs)', cred: 0.85, type: 'FACT', claim: 'cut' }, { src: 'Wire service', cred: 0.9, type: 'FACT', claim: 'cut' }, { src: 'Broker note', cred: 0.6, type: 'PREDICTION', claim: 'deal flow' }],
      secondOrder: [{ variable: 'bond_yield', label: 'Government bond yields', unit: 'bps', magnitude: -10, sigma: 0.77, hit: 0.55, path: ['Technology budgets -8%', 'IT exports and hiring soften', 'Growth expectations lower, yields about -10 bps'] }] },
    { id: 'ev', title: 'EV share of new cars rises by 6 points', keys: ['ev', 'electric', 'electric vehicle', 'ev share'], tags: ['Technology change'], date: '2026-09-29', horizonQ: 3, horizonText: '2 to 4 quarters',
      variable: { name: 'ev_share', label: 'EV share of new cars', unit: 'pts', magnitude: 6 }, sigmaE: 0.40, hit: 0.60,
      precedents: [{ title: 'China 2020 to 2023 EV adoption', sim: 0.62, outcome: 'EV-led OEMs gained share; fuel demand growth slowed' }],
      sources: [{ src: 'Registration data (VAHAN)', cred: 0.95, type: 'FACT', claim: 'share' }, { src: 'Wire service', cred: 0.9, type: 'FACT', claim: 'share' }, { src: 'Consultant report', cred: 0.6, type: 'PREDICTION', claim: 'trajectory' }, { src: 'Social media post', cred: 0.3, type: 'CLAIM', claim: 'share', conflict: true }] },
  ];

  // Channel fields: variable, kind (cost | revenue | finance | demand | treasury), share (of revenue), beta, sigmaC, passThrough, lagQ, hedge, substitution, policyRisk, source (disclosed | estimated | second-order), basis
  // kind decides the transmission factor T: cost and demand -> (1 - passThrough); revenue, finance and treasury -> passThrough; all x (1 - hedge) x (1 - substitution)
  const COMPANIES = [
    { id: 'indigo', name: 'IndiGo', sector: 'Airline', margin: 0.29, asOf: '2026-06-30', desc: 'Sells air tickets; largest domestic airline. Fuel is the biggest cost line and is only partly hedged.',
      channels: [{ variable: 'crude', kind: 'cost', name: 'Aviation fuel', share: 0.37, beta: 0.880, sigmaC: 0.228, passThrough: 0.45, lagQ: 1, hedge: 0.20, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Fuel 37% of revenue, ATF moves about 0.7x crude, EBITDAR margin 29%' }] },
    { id: 'spicejet', name: 'SpiceJet', sector: 'Airline', margin: 0.12, asOf: '2026-06-30', desc: 'Sells air tickets; low-cost carrier with a thin margin and almost no fuel hedging.',
      channels: [{ variable: 'crude', kind: 'cost', name: 'Aviation fuel', share: 0.40, beta: 0.723, sigmaC: 0.221, passThrough: 0.40, lagQ: 1, hedge: 0.05, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Fuel 40% of revenue, thin margin amplifies the percentage effect' }] },
    { id: 'airindia', name: 'Air India', sector: 'Airline', margin: 0.15, asOf: '2026-06-30', desc: 'Sells air tickets; full-service carrier with a large international network and a sizeable fuel hedge.',
      channels: [{ variable: 'crude', kind: 'cost', name: 'Aviation fuel', share: 0.35, beta: 0.848, sigmaC: 0.236, passThrough: 0.42, lagQ: 1, hedge: 0.42, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Fuel 35% of revenue, 42% hedged for the next two quarters' }] },
    { id: 'ongc', name: 'ONGC', sector: 'Oil and gas', margin: 0.45, asOf: '2026-06-30', desc: 'Oil and gas producer; realisations track crude but a windfall levy caps the upside.',
      channels: [{ variable: 'crude', kind: 'revenue', name: 'Crude realisations', share: 0.75, beta: 0.714, sigmaC: 0.421, passThrough: 0.82, lagQ: 1, hedge: 0.12, substitution: 0, policyRisk: 0.40, source: 'disclosed', basis: 'Company sensitivity table: EBITDA per $1/bbl; 82% captured after the windfall levy' },
        { variable: 'ev_share', kind: 'demand', signUp: -1, name: 'Domestic fuel demand', share: 0.75, beta: 0.299, sigmaC: 0.549, passThrough: 0.20, lagQ: 2, hedge: 0.12, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Petrol demand growth slows about 0.5 pp per EV share point' }] },
    { id: 'oilindia', name: 'Oil India', sector: 'Oil and gas', margin: 0.42, asOf: '2026-06-30', desc: 'Oil and gas producer in the north-east; realisations track crude.',
      channels: [{ variable: 'crude', kind: 'revenue', name: 'Crude realisations', share: 0.70, beta: 0.520, sigmaC: 0.402, passThrough: 0.80, lagQ: 1, hedge: 0.10, substitution: 0, policyRisk: 0.30, source: 'estimated', basis: 'Realisations 70% of revenue; windfall levy applies above a threshold' }] },
    { id: 'ioc', name: 'Indian Oil', sector: 'Oil refining and marketing', margin: 0.08, asOf: '2026-06-30', desc: 'Refiner and fuel retailer; crude is the input and retail prices lag.',
      channels: [{ variable: 'crude', kind: 'cost', name: 'Crude input', share: 0.85, beta: 0.481, sigmaC: 0.228, passThrough: 0.30, lagQ: 1, hedge: 0.08, substitution: 0, policyRisk: 0.2, source: 'estimated', basis: 'Retail price lag; marketing margin absorbs the first weeks' }] },
    { id: 'bpcl', name: 'BPCL', sector: 'Oil refining and marketing', margin: 0.09, asOf: '2026-06-30', desc: 'Refiner and fuel retailer with a larger hedge book than peers.',
      channels: [{ variable: 'crude', kind: 'cost', name: 'Crude input', share: 0.84, beta: 0.441, sigmaC: 0.238, passThrough: 0.35, lagQ: 1, hedge: 0.14, substitution: 0, policyRisk: 0.2, source: 'estimated', basis: 'Retail price lag; 14% of crude purchases hedged' }] },
    { id: 'vedanta', name: 'Vedanta', sector: 'Metals and mining', margin: 0.30, asOf: '2026-06-30', desc: 'Diversified metals and oil producer: zinc, aluminium, iron ore and Cairn oil.',
      channels: [{ variable: 'steel', kind: 'revenue', name: 'Iron ore and metal realisations', share: 0.55, beta: 0.442, sigmaC: 0.347, passThrough: 0.80, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Iron ore and ferrous realisations track steel with a one-quarter lag' },
        { variable: 'crude', kind: 'revenue', name: 'Oil and gas realisations (Cairn)', share: 0.20, beta: 0.323, sigmaC: 0.351, passThrough: 0.70, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0.2, source: 'estimated', basis: 'Cairn oil about 20% of revenue, net of profit petroleum and levy' }] },
    { id: 'hdfc', name: 'HDFC Bank', sector: 'Bank', margin: 0.55, asOf: '2026-06-30', desc: 'Private sector bank; net interest margin widens when policy rates rise.',
      channels: [{ variable: 'rate', kind: 'finance', name: 'Net interest margin', share: 0.80, beta: 8.081, sigmaC: 0.402, passThrough: 0.70, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'disclosed', basis: 'Interest-rate sensitivity table: NII +5.7% per 100 bps; 70% of the policy move reaches the book' },
        { variable: 'bond_yield', kind: 'treasury', name: 'Treasury book (AFS) mark-to-market', share: 0.10, beta: 3.7, sigmaC: 0.38, passThrough: 1.0, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'second-order', basis: 'AFS book duration about 2.5 years; +3.7% of PPOP per 100 bps fall in yields' }] },
    { id: 'icici', name: 'ICICI Bank', sector: 'Bank', margin: 0.55, asOf: '2026-06-30', desc: 'Private sector bank with a large floating-rate loan book.',
      channels: [{ variable: 'rate', kind: 'finance', name: 'Net interest margin', share: 0.80, beta: 6.788, sigmaC: 0.402, passThrough: 0.75, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'disclosed', basis: 'Interest-rate sensitivity table; 75% of the policy move reaches the book' }] },
    { id: 'sbi', name: 'State Bank of India', sector: 'Bank', margin: 0.50, asOf: '2026-06-30', desc: 'Largest public sector bank; deposit franchise reprices slowly.',
      channels: [{ variable: 'rate', kind: 'finance', name: 'Net interest margin', share: 0.80, beta: 6.171, sigmaC: 0.402, passThrough: 0.55, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'disclosed', basis: 'Interest-rate sensitivity table; 55% of the policy move reaches the book' }] },
    { id: 'axis', name: 'Axis Bank', sector: 'Bank', margin: 0.52, asOf: '2026-06-30', desc: 'Private sector bank; corporate and retail lending.',
      channels: [{ variable: 'rate', kind: 'finance', name: 'Net interest margin', share: 0.80, beta: 6.465, sigmaC: 0.402, passThrough: 0.70, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'disclosed', basis: 'Interest-rate sensitivity table; 70% of the policy move reaches the book' }] },
    { id: 'maruti', name: 'Maruti Suzuki', sector: 'Car manufacturer', margin: 0.12, asOf: '2026-06-30', desc: 'Largest car maker; steel is the biggest raw material and buyers depend on car loans.',
      channels: [{ variable: 'steel', kind: 'cost', name: 'Steel and raw materials', share: 0.33, beta: 0.253, sigmaC: 0.382, passThrough: 0.40, lagQ: 1, hedge: 0.05, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Raw materials 33% of revenue, steel about half of that' },
        { variable: 'rate', kind: 'demand', signUp: -1, name: 'Car-loan financed demand', share: 0.80, beta: 4.041, sigmaC: 0.402, passThrough: 0.30, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: '80% of sales financed; volumes fall about 1% per 50 bps' }] },
    { id: 'tata', name: 'Tata Motors', sector: 'Car manufacturer', margin: 0.13, asOf: '2026-06-30', desc: 'Car, EV and truck maker; leads domestic EV sales.',
      channels: [{ variable: 'ev_share', kind: 'revenue', name: 'EV volume and mix', share: 0.15, beta: 0.673, sigmaC: 0.323, passThrough: 0.70, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'EV share of domestic sales about 70% of the incremental EV market' },
        { variable: 'steel', kind: 'cost', name: 'Steel and raw materials', share: 0.35, beta: 0.238, sigmaC: 0.347, passThrough: 0.45, lagQ: 1, hedge: 0.10, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Raw materials 35% of revenue' }] },
    { id: 'hero', name: 'Hero MotoCorp', sector: 'Two-wheeler manufacturer', margin: 0.14, asOf: '2026-06-30', desc: 'Largest two-wheeler maker; exposed to steel and to the shift to electric scooters.',
      channels: [{ variable: 'steel', kind: 'cost', name: 'Steel and raw materials', share: 0.30, beta: 0.223, sigmaC: 0.347, passThrough: 0.26, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Raw materials 30% of revenue; price revisions lag a quarter' },
        { variable: 'ev_share', kind: 'demand', signUp: -1, name: 'Petrol two-wheeler demand', share: 0.90, beta: 0.184, sigmaC: 0.511, passThrough: 0.30, lagQ: 2, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Electric scooters take share from entry petrol models' }] },
    { id: 'sun', name: 'Sun Pharmaceutical', sector: 'Pharmaceutical', margin: 0.28, asOf: '2026-06-30', desc: 'Largest drug maker; imports intermediates and sells price-controlled essential drugs.',
      channels: [{ variable: 'intermediate', kind: 'cost', name: 'Imported intermediates', share: 0.22, beta: 0.299, sigmaC: 0.312, passThrough: 0.30, lagQ: 1, hedge: 0.10, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Intermediates 22% of revenue' },
        { variable: 'drug_price', kind: 'demand', name: 'Price-controlled portfolio', share: 0.25, beta: 0.331, sigmaC: 0.391, passThrough: 0.20, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Essential drugs about 25% of domestic revenue; mix shift offsets 20%' },
        { variable: 'rate', kind: 'finance', signUp: -1, name: 'Floating-rate debt', share: 0.05, beta: 1.732, sigmaC: 0.683, passThrough: 0.20, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Net debt small relative to EBITDA' }] },
    { id: 'divis', name: "Divi's Laboratories", sector: 'Pharmaceutical', margin: 0.33, asOf: '2026-06-30', desc: 'Makes active ingredients and intermediates in India; gains when imported supply is restricted.',
      channels: [{ variable: 'intermediate', kind: 'revenue', name: 'Domestic intermediate sales', share: 0.60, beta: 0.377, sigmaC: 0.312, passThrough: 0.75, lagQ: 1, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Domestic API and intermediate pricing follows import parity' }] },
    { id: 'tcs', name: 'TCS', sector: 'IT services', margin: 0.26, asOf: '2026-06-30', desc: 'Largest IT services exporter; revenue follows enterprise technology budgets.',
      channels: [{ variable: 'tech_budget', kind: 'demand', name: 'Enterprise services demand', share: 0.95, beta: 0.295, sigmaC: 0.328, passThrough: 0.10, lagQ: 2, hedge: 0, substitution: 0, policyRisk: 0, source: 'estimated', basis: 'Revenue elasticity to client budgets about 0.4 with a two-quarter lag' }] },
  ];

  // ------------------------------------------------------------------ search
  const norm = s => String(s || '').toLowerCase().trim();
  function findEvents(q) { const n = norm(q); if (!n) return []; return EVENTS.filter(e => norm(e.title).includes(n) || e.keys.some(k => k.includes(n) || n.includes(k) && n.length >= 3)); }
  function findCompanies(q) { const n = norm(q); if (!n) return []; return COMPANIES.filter(c => norm(c.name + ' ' + c.sector + ' ' + c.desc).includes(n)); }
  const eventById = id => EVENTS.find(e => e.id === id);
  const companyById = id => COMPANIES.find(c => c.id === id);

  // ------------------------------------------------------------------ source verification
  function verify(ev) {
    const groups = {}; ev.sources.forEach(s => { (groups[s.claim] = groups[s.claim] || []).push(s); });
    const rows = ev.sources.map(s => { const corroboration = groups[s.claim].filter(o => o !== s && !o.conflict).length; const conf = s.conflict ? r2(s.cred * 0.4) : r2(clamp(s.cred * (1 + 0.08 * corroboration), 0, 0.99)); return { ...s, corroboration, conf, status: s.conflict ? 'CONFLICT' : s.type }; });
    const facts = rows.filter(r => r.type === 'FACT' && !r.conflict);
    const sourceConfidence = r2(facts.reduce((a, r) => a + r.conf, 0) / Math.max(1, facts.length));
    return { rows, facts: facts.length, conflicts: rows.filter(r => r.conflict).length, sourceConfidence };
  }

  // ------------------------------------------------------------------ channel mapping (first and second order)
  function channelsFor(ev, co) {
    const out = [];
    co.channels.filter(c => c.variable === ev.variable.name).forEach(c => out.push({ ...c, order: 1, move: ev.variable, sigmaE: ev.sigmaE, hit: ev.hit, path: null }));
    (ev.secondOrder || []).forEach(link => co.channels.filter(c => c.variable === link.variable).forEach(c => out.push({ ...c, order: 2, move: { name: link.variable, label: link.label, unit: link.unit, magnitude: link.magnitude }, sigmaE: link.sigma, hit: link.hit, path: link.path })));
    return out;
  }
  const unitScale = u => u === 'bps' ? 1 / 100 : 1; // betas for rate-type variables are per 100 bps
  function transmission(c, horizonQ) { const pEff = c.passThrough * Math.min(1, horizonQ / Math.max(1, c.lagQ)); const base = (c.kind === 'cost' || c.kind === 'demand') ? (1 - pEff) : pEff; return { T: base * (1 - c.hedge) * (1 - c.substitution), pEff }; }
  // Sign of the EBITDA effect when the variable rises: cost and treasury default to adverse (-1), revenue, finance and demand default to supportive (+1); a channel can override with signUp.
  const SIGN_UP = { cost: -1, treasury: -1, revenue: 1, finance: 1, demand: 1 };
  function channelSign(c) { const signUp = c.signUp !== undefined ? c.signUp : SIGN_UP[c.kind]; return (c.move.magnitude > 0 ? 1 : -1) * signUp; }
  function channelMedian(c, horizonQ) { const { T } = transmission(c, horizonQ); return channelSign(c) * c.beta * Math.abs(c.move.magnitude) * unitScale(c.move.unit) * T; }

  // ------------------------------------------------------------------ Monte Carlo transmission
  function simulate(ev, co, chans, opts) {
    const N = (opts && opts.draws) || 8000; const half = N / 2;
    const rng = mulberry32(hash(ev.id + '|' + co.id) || 1);
    const shockZ = {}; const total = new Float64Array(N); const perChannel = [];
    chans.forEach(c => {
      const key = c.move.name; if (!shockZ[key]) { const z = gaussians(rng, half); const full = new Float64Array(N); for (let i = 0; i < half; i++) { full[i] = z[i]; full[i + half] = -z[i]; } shockZ[key] = full; }
      const zb = gaussians(rng, half); const med = channelMedian(c, ev.horizonQ); const draws = new Float64Array(N);
      for (let i = 0; i < half; i++) { const m1 = Math.exp(c.sigmaE * shockZ[key][i]), m2 = Math.exp(c.sigmaE * shockZ[key][i + half]); const b1 = Math.exp(c.sigmaC * zb[i]), b2 = Math.exp(-c.sigmaC * zb[i]); draws[i] = med * m1 * b1; draws[i + half] = med * m2 * b2; }
      for (let i = 0; i < N; i++) total[i] += draws[i];
      perChannel.push({ channel: c, median: r3(med) });
    });
    const sorted = Array.from(total).sort((a, b) => a - b);
    const median = quantile(sorted, 0.5); const mean = sorted.reduce((a, b) => a + b, 0) / N;
    const sign = median < 0 ? -1 : 1; let pSign = 0, pGe1 = 0, pGe04 = 0; for (let i = 0; i < N; i++) { if (sign * total[i] > 0) pSign++; const a = Math.abs(total[i]); if (a >= 1) pGe1++; if (a >= 0.4) pGe04++; }
    return { N, sorted, median, mean, pSign: pSign / N, pGe1: pGe1 / N, pGe04: pGe04 / N, perChannel, q: p => quantile(sorted, p) };
  }

  // ------------------------------------------------------------------ scenarios, materiality
  function baseProbability(chans) { const c = chans.reduce((a, b) => Math.abs(channelMedian(b, 2)) > Math.abs(channelMedian(a, 2)) ? b : a); return { p: r2(clamp(0.55 + 0.5 * (c.hit - 0.70) - 0.30 * (c.policyRisk || 0), 0.30, 0.70)), primary: c }; }
  // Base case is the central pBase mass of the simulated distribution. The favourable tail (less loss or more gain) is the upside case, the other tail the downside case; policy risk weights the downside tail.
  function scenarios(sim, pBase, primary) {
    const lo = sim.q(0.5 - pBase / 2), hi = sim.q(0.5 + pBase / 2); const tail = 1 - pBase; const skew = 0.5 * (primary.policyRisk || 0); const adverse = sim.median < 0;
    const upper = { lo: hi, hi: sim.q(0.99) }, lower = { lo: sim.q(0.01), hi: lo };
    const base = { name: 'Base case', p: pBase, lo, hi, why: 'Central band of the simulated distribution' };
    const up = { name: 'Upside case', p: r2(tail * (0.5 - skew)), ...upper, why: adverse ? 'Shock fades or you pass more on' : 'Move extends in your favour' };
    const down = { name: 'Downside case', p: r2(tail * (0.5 + skew)), ...lower, why: adverse ? 'Shock persists and pass-through stalls' : 'Gain fades or policy claws it back' };
    return { list: [base, up, down].map(s => ({ ...s, lo: r2(s.lo), hi: r2(s.hi) })), band: { lo: r2(lo), hi: r2(hi), pBase }, expected: r2(sim.mean) };
  }
  function materiality(sim) { const tier = sim.pGe1 >= 0.6 ? 'high' : sim.pGe04 >= 0.6 ? 'medium' : 'low'; return { tier, pGe1: r2(sim.pGe1), pGe04: r2(sim.pGe04), rule: 'high if P(|impact| >= 1% of EBITDA) >= 60%; medium if P(|impact| >= 0.4%) >= 60%; else low' }; }

  // ------------------------------------------------------------------ confidence: components, raw score, isotonic calibration on the ledger
  const SOURCE_Q = { disclosed: 0.92, estimated: 0.72, 'second-order': 0.50 };
  function recordAge(asOf) { const d = (Date.now() - new Date(asOf + 'T00:00:00').getTime()) / 86400000; return d <= 365 ? 1 : d <= 730 ? 0.9 : 0.8; }
  function rawConfidence(ver, chans, sim, co) {
    const primary = chans.reduce((a, b) => Math.abs(channelMedian(b, 2)) > Math.abs(channelMedian(a, 2)) ? b : a);
    const comps = [
      { name: 'Source verification', value: ver.sourceConfidence, weight: 0.15, note: `${ver.facts} confirmed facts, ${ver.conflicts} conflict${ver.conflicts === 1 ? '' : 's'} set aside` },
      { name: 'Precedent direction hit rate', value: r2(primary.hit), weight: 0.40, note: primary.order === 2 ? 'Second-order link; thin precedent set' : 'Same event type in the precedent ledger' },
      { name: 'Sign agreement across channels', value: r2(sim.pSign), weight: 0.10, note: chans.length > 1 ? `${chans.length} channels, ${Math.round(sim.pSign * 100)}% of draws share the sign` : 'Single channel' },
      { name: 'Company record quality', value: r2(SOURCE_Q[primary.source] * recordAge(co.asOf)), weight: 0.25, note: `${primary.source} elasticity, record as of ${co.asOf}` },
      { name: 'Magnitude clarity', value: r2(1 / (1 + primary.sigmaE)), weight: 0.10, note: `Realised move dispersion ${Math.round(primary.sigmaE * 100)}%` },
    ];
    const raw = r3(Math.exp(comps.reduce((a, c) => a + c.weight * Math.log(Math.max(0.01, c.value)), 0)));
    const sizeGrade = primary.sigmaC <= 0.25 && primary.source === 'disclosed' ? 'A' : primary.sigmaC <= 0.45 && primary.order === 1 ? 'B' : 'C';
    const sizeNote = { A: 'Disclosed sensitivity, tight elasticity', B: 'Elasticity estimated from filings; range width is the honest spread', C: 'Second-order or wide elasticity; use the direction, not the size' }[sizeGrade];
    return { comps, raw, primary, sizeGrade, sizeNote };
  }

  // Backtest ledger: past (event type, company) calls with the raw score the engine produced at T0 and the realised direction. Generated deterministically here; the production build loads the frozen ledger.
  function ledger() {
    const rng = mulberry32(20261016); const out = []; const types = ['crude', 'rate', 'steel', 'pharma', 'regulation', 'demand', 'ev'];
    for (let i = 0; i < 160; i++) { const raw = r3(0.40 + 0.55 * rng()); const pTrue = clamp(0.12 + 0.80 * raw, 0, 0.97); const hit = rng() < pTrue ? 1 : 0; out.push({ id: 'L' + (i + 1), type: types[i % types.length], asOf: 2019 + (i % 7), raw, hit, sizeRatio: r2(0.4 + 1.4 * rng()) }); }
    return out;
  }
  const LEDGER = ledger();
  function evaluate(ledger) {
    const L = ledger || LEDGER; const pairs = L.map(x => [x.raw, x.hit]); const iso = isotonic(pairs); const pl = platt(pairs);
    const brierRaw = L.reduce((a, x) => a + Math.pow(x.raw - x.hit, 2), 0) / L.length; const brierCal = L.reduce((a, x) => a + Math.pow(pl.predict(x.raw) - x.hit, 2), 0) / L.length;
    const bins = Array.from({ length: 10 }, (_, k) => ({ lo: k / 10, hi: (k + 1) / 10, n: 0, conf: 0, hit: 0 }));
    L.forEach(x => { const b = bins[Math.min(9, Math.floor(x.raw * 10))]; b.n++; b.conf += x.raw; b.hit += x.hit; });
    const eceRaw = bins.reduce((a, b) => a + (b.n ? b.n / L.length * Math.abs(b.conf / b.n - b.hit / b.n) : 0), 0);
    const binsCal = Array.from({ length: 10 }, (_, k) => ({ lo: k / 10, hi: (k + 1) / 10, n: 0, conf: 0, hit: 0 }));
    L.forEach(x => { const p = pl.predict(x.raw); const b = binsCal[Math.min(9, Math.floor(p * 10))]; b.n++; b.conf += p; b.hit += x.hit; });
    const eceCal = binsCal.reduce((a, b) => a + (b.n ? b.n / L.length * Math.abs(b.conf / b.n - b.hit / b.n) : 0), 0);
    const hitRate = L.reduce((a, x) => a + x.hit, 0) / L.length; const sizeWithin = L.filter(x => x.sizeRatio >= 0.5 && x.sizeRatio <= 2).length / L.length;
    return { n: L.length, hitRate: r2(hitRate), brierRaw: r3(brierRaw), brierCal: r3(brierCal), eceRaw: r3(eceRaw), eceCal: r3(eceCal), sizeWithin2x: r2(sizeWithin), bins: bins.map(b => ({ lo: b.lo, hi: b.hi, n: b.n, conf: b.n ? r2(b.conf / b.n) : null, hit: b.n ? r2(b.hit / b.n) : null })), iso, platt: pl, note: 'Direction is scored against realised outcomes; size is reported as the share of calls whose realised size fell within 0.5x to 2x of the estimate.' };
  }
  let CAL = null; function calibrator() { if (!CAL) CAL = evaluate().platt; return CAL; }

  // ------------------------------------------------------------------ decision layer
  function levers(ev, co, chans, result) {
    const out = []; const primary = result.confidence.primary; if (primary.order !== 1) return out;
    const rerun = mod => { const c2 = chans.map(c => c === primary ? { ...c, ...mod } : c); const s = simulate(ev, co, c2, { draws: 4000 }); return s.median; };
    const base = result.dist.median; const adverse = base < 0; const m = co.margin; const share = primary.share;
    const add = (label, how, after, cost, note) => { const benefit = adverse ? (after - base) : (after - base); out.push({ label, how, benefit: r2(benefit), cost: r2(cost), net: r2(benefit - cost), note }); };
    if (adverse && (primary.kind === 'cost' || primary.kind === 'finance')) {
      const h = Math.min(1, primary.hedge + 0.30); const premium = 0.25 * primary.sigmaE; // annual premium as a share of hedged notional, scaled by expected dispersion
      add('Hedge 30 points more of ' + primary.name.toLowerCase(), 'Forward or swap on an extra 30% of the exposure', rerun({ hedge: h }), 100 * (0.30 * share * premium * 0.25) / m, 'Cost: option or forward premium on the extra notional, one quarter');
      if (primary.kind === 'cost' && !/fuel|power|freight/i.test(primary.name)) add('Pre-buy 8 weeks of ' + primary.name.toLowerCase(), 'Buy ahead before prices reset', base + Math.abs(base) * (8 / 13) / 4, 100 * (share * (8 / 52) * 0.10 * (8 / 52)) / m, 'Cost: working-capital interest at 10% a year');
      if (primary.kind === 'cost') { const p2 = Math.min(1, primary.passThrough + 0.20); const after = rerun({ passThrough: p2 }); add('Pass 20 points more through to customers', 'Price revision or surcharge clause', after, 0.25 * (after - base), 'Cost: volume lost to the price rise, assumed at a quarter of the gain'); }
      if (primary.kind === 'finance') add('Swap floating debt to fixed', 'Interest-rate swap on half the book', rerun({ hedge: Math.min(1, primary.hedge + 0.5) }), 100 * (0.5 * share * 0.002) / m, 'Cost: swap spread about 20 bps');
    } else if (adverse && primary.kind === 'demand') {
      const after = rerun({ passThrough: Math.min(1, primary.passThrough + 0.20) }); add('Flex costs to offset 20 points more of the shortfall', 'Hiring freeze, discretionary spend, pyramid', after, 0.3 * (after - base), 'Cost: restructuring and lost capacity, assumed at 30% of the gain');
    } else if (!adverse) {
      const s = result.scenarios.list; const down = s[2], up = s[1]; const downMid = (down.lo + down.hi) / 2, upMid = (up.lo + up.hi) / 2;
      out.push({ label: 'Lock in prices for the next quarter', how: 'Fixed-price contracts or forward sales on half the exposed volume', benefit: r2(0.5 * down.p * (base - downMid)), cost: r2(0.5 * up.p * (upMid - base)), net: r2(0.5 * down.p * (base - downMid) - 0.5 * up.p * (upMid - base)), note: 'Benefit: downside avoided; cost: upside forgone, on the locked half' });
      if (primary.kind === 'revenue') out.push({ label: 'Hold inventory purchases steady', how: 'Do not buy inputs at the top of the move', benefit: 0, cost: 0, net: 0, note: 'No cost; avoids locking in a reversal' });
    }
    return out.sort((a, b) => b.net - a.net);
  }
  function decide(result) {
    const m = result.materiality.tier, c = result.confidence.calibrated, t = result.timeToImpactQ;
    let verdict, reason;
    if (!result.exposed) { verdict = 'Ignore'; reason = 'No channel links this event to the company.'; }
    else if (m === 'high' && c >= 0.65 && t <= 2) { verdict = 'Act'; reason = 'Material, direction confidence above 65%, impact within two quarters.'; }
    else if (m === 'high' || (m === 'medium' && c >= 0.55)) { verdict = 'Prepare'; reason = m === 'high' ? 'Material but confidence or timing does not yet justify spending on a hedge.' : 'Moderate effect with reasonable confidence; line up the response.'; }
    else { verdict = 'Monitor'; reason = 'Small or uncertain effect; re-run when the next reading arrives.'; }
    const top = result.levers.find(l => l.net > 0) || null; if (verdict === 'Act' && !top) reason += ' No lever beats holding the position; keep it and watch the downside readings.';
    return { verdict, reason, top, score: r2(({ high: 1, medium: 0.6, low: 0.2 })[m] * c * (t <= 1 ? 1 : t <= 2 ? 0.8 : 0.6)) };
  }

  // ------------------------------------------------------------------ assess
  function assess(ev, co, opts) {
    const ver = verify(ev); const chans = channelsFor(ev, co);
    const trace = [];
    trace.push({ step: 'Search and tokenise', text: `Event "${ev.title}" tokenised: variable ${ev.variable.label} ${ev.variable.magnitude > 0 ? '+' : ''}${ev.variable.magnitude} ${ev.variable.unit}, dated ${ev.date}, horizon ${ev.horizonText}.` });
    trace.push({ step: 'Verify sources', text: `${ev.sources.length} sources checked: ${ver.facts} confirmed facts, ${ver.conflicts} conflicting report${ver.conflicts === 1 ? '' : 's'} set aside. Source confidence ${Math.round(ver.sourceConfidence * 100)}%.` });
    trace.push({ step: 'Classify', text: `Tags: ${ev.tags.join(', ')}.` });
    if (!chans.length) {
      trace.push({ step: 'Map channels', text: `No cost, revenue, financing or demand line of ${co.name} moves with ${ev.variable.label}, and no second-order link applies.` });
      return { ev, co, exposed: false, direction: null, materiality: { tier: 'none' }, note: `No channel links ${ev.title.toLowerCase()} to ${co.name}.`, trace, ver, channels: [] };
    }
    trace.push({ step: 'Map channels', text: chans.map(c => `${c.name} (${c.kind}, ${c.order === 1 ? 'first order' : 'second order via ' + c.path.join(' > ')}): beta ${c.beta} per ${c.move.unit === 'bps' ? '100 bps' : '1 ' + c.move.unit}, pass-through ${Math.round(c.passThrough * 100)}%, hedge ${Math.round(c.hedge * 100)}%, lag ${c.lagQ}Q.`).join(' ') });
    trace.push({ step: 'Shock distribution', text: chans.map(c => `${c.move.label}: lognormal around ${c.move.magnitude > 0 ? '+' : ''}${c.move.magnitude} ${c.move.unit}, dispersion ${Math.round(c.sigmaE * 100)}%; elasticity uncertainty ${Math.round(c.sigmaC * 100)}%.`).join(' ') });
    trace.push({ step: 'Transmission', text: chans.map(c => { const t = transmission(c, ev.horizonQ); return `${c.name}: T = ${c.kind === 'cost' || c.kind === 'demand' ? '(1 - ' + Math.round(t.pEff * 100) + '% pass-through)' : Math.round(t.pEff * 100) + '% captured'} x (1 - ${Math.round(c.hedge * 100)}% hedge) x (1 - ${Math.round(c.substitution * 100)}% substitution) = ${r3(t.T)}; median ${r2(channelMedian(c, ev.horizonQ))}% of EBITDA.`; }).join(' ') });
    const sim = simulate(ev, co, chans, opts);
    trace.push({ step: 'Monte Carlo', text: `${sim.N} antithetic draws (seed from event and company ids). Median ${r2(sim.median)}%, mean ${r2(sim.mean)}%, P10 ${r2(sim.q(0.1))}%, P90 ${r2(sim.q(0.9))}%.` });
    const { p: pBase, primary } = baseProbability(chans);
    const sc = scenarios(sim, pBase, primary);
    trace.push({ step: 'Scenario bands', text: `Base probability ${Math.round(pBase * 100)}% = 55% + 0.5 x (precedent hit rate ${primary.hit} - 0.70) - 0.3 x policy risk ${primary.policyRisk || 0}. Base band is the central ${Math.round(pBase * 100)}% of draws: ${sc.band.lo}% to ${sc.band.hi}%.` });
    const mat = materiality(sim);
    trace.push({ step: 'Materiality', text: `P(|impact| >= 1%) = ${Math.round(mat.pGe1 * 100)}%, P(|impact| >= 0.4%) = ${Math.round(mat.pGe04 * 100)}%: ${mat.tier}.` });
    const rc = rawConfidence(ver, chans, sim, co); const calibrated = r2(calibrator().predict(rc.raw));
    trace.push({ step: 'Confidence', text: `Weighted components ${rc.comps.map(c => c.name.toLowerCase() + ' ' + Math.round(c.value * 100) + '%').join(', ')} give a raw direction score of ${Math.round(rc.raw * 100)}%; logistic calibration on the ledger maps it to ${Math.round(calibrated * 100)}%. Size reliability ${rc.sizeGrade}.` });
    const direction = sim.median < 0 ? 'adverse' : 'supportive';
    const timeToImpactQ = Math.min(...chans.map(c => c.kind === 'cost' ? 1 : c.lagQ));
    const result = { ev, co, exposed: true, direction, channels: chans.map((c, i) => ({ ...c, median: sim.perChannel[i].median, T: r3(transmission(c, ev.horizonQ).T) })), dist: { median: r2(sim.median), mean: r2(sim.mean), p10: r2(sim.q(0.1)), p25: r2(sim.q(0.25)), p75: r2(sim.q(0.75)), p90: r2(sim.q(0.9)), pSign: r2(sim.pSign) }, band: sc.band, scenarios: sc, expected: sc.expected, materiality: mat, confidence: { comps: rc.comps, raw: rc.raw, calibrated, sizeGrade: rc.sizeGrade, sizeNote: rc.sizeNote, primary }, passThrough: primary.passThrough, hedge: primary.hedge, primary, timeToImpactQ, ver, trace };
    result.levers = levers(ev, co, chans, result);
    result.decision = decide(result);
    trace.push({ step: 'Levers and decision', text: result.levers.length ? `${result.levers.length} levers priced by re-running the simulation with one change each; best net ${result.levers[0].net > 0 ? '+' : ''}${result.levers[0].net}% of EBITDA (${result.levers[0].label}). Verdict: ${result.decision.verdict}.` : `No lever applies. Verdict: ${result.decision.verdict}.` });
    trace.push({ step: 'Evaluation', text: 'Direction can be checked against the precedent ledger and is scored there; the size is a transparent estimate from the company record and is not taken from history.' });
    return result;
  }

  // ------------------------------------------------------------------ property tests (engine invariants)
  function propertyTests() {
    const out = []; const ev = eventById('crude'), co = companyById('indigo');
    const t = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const a = assess(ev, co); const b = assess(ev, { ...co, channels: co.channels.map(c => ({ ...c, hedge: Math.min(1, c.hedge + 0.3) })) });
    t('More hedge never increases the loss', Math.abs(b.dist.median) < Math.abs(a.dist.median), `${a.dist.median}% vs ${b.dist.median}% with +30 pts hedge`);
    const z = assess({ ...ev, variable: { ...ev.variable, magnitude: 0 } }, co);
    t('Zero shock gives zero impact', Math.abs(z.dist.median) < 1e-9 && z.materiality.tier === 'low', `median ${z.dist.median}%`);
    const d = assess({ ...ev, variable: { ...ev.variable, magnitude: 20 } }, co);
    t('Doubling the shock doubles the median', Math.abs(d.dist.median / a.dist.median - 2) < 0.05, `${a.dist.median}% -> ${d.dist.median}%`);
    const f = assess({ ...ev, variable: { ...ev.variable, magnitude: -10 } }, co);
    t('Flipping the shock flips the direction', f.direction === 'supportive' && a.direction === 'adverse', `${a.direction} -> ${f.direction}`);
    const p = assess(ev, { ...co, channels: co.channels.map(c => ({ ...c, passThrough: Math.min(1, c.passThrough + 0.3) })) });
    t('More pass-through never increases the loss', Math.abs(p.dist.median) < Math.abs(a.dist.median), `${a.dist.median}% vs ${p.dist.median}%`);
    const h1 = assess(eventById('regulation'), companyById('sun')), h2 = assess(eventById('regulation'), companyById('hdfc'));
    t('Second-order channels carry lower confidence than first-order', h2.confidence.calibrated < h1.confidence.calibrated, `${h1.confidence.calibrated} first order vs ${h2.confidence.calibrated} second order`);
    const r1x = assess(ev, co), r2x = assess(ev, co);
    t('Same inputs give the same outputs (seeded)', r1x.band.lo === r2x.band.lo && r1x.band.hi === r2x.band.hi && r1x.confidence.calibrated === r2x.confidence.calibrated, `${r1x.band.lo} to ${r1x.band.hi}`);
    const m1 = assess({ ...ev, variable: { ...ev.variable, magnitude: 2 } }, co), m2 = assess({ ...ev, variable: { ...ev.variable, magnitude: 6 } }, co);
    t('Materiality is monotone in the shock', ['low', 'medium', 'high'].indexOf(m1.materiality.tier) <= ['low', 'medium', 'high'].indexOf(m2.materiality.tier) && ['low', 'medium', 'high'].indexOf(m2.materiality.tier) <= 2, `${m1.materiality.tier} at +2%, ${m2.materiality.tier} at +6%, ${a.materiality.tier} at +10%`);
    const ev2 = evaluate(); t('Calibration does not worsen the Brier score', ev2.brierCal <= ev2.brierRaw + 1e-9, `Brier ${ev2.brierRaw} raw -> ${ev2.brierCal} calibrated`);
    t('Calibration is monotone', ev2.platt.b > 0 && ev2.iso.steps.every((s, i, arr) => i === 0 || s.y >= arr[i - 1].y), `slope ${ev2.platt.b}; ${ev2.iso.steps.length} isotonic steps`);
    return out;
  }

  return { TAGS, EVENTS, COMPANIES, LEDGER, findEvents, findCompanies, eventById, companyById, verify, channelsFor, transmission, channelMedian, simulate, assess, evaluate, propertyTests, isotonic, qnorm, version: '0.3.0' };
});
