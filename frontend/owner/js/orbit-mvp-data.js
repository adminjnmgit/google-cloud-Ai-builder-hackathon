/* Orbit MVP data layer: variables, variables for all fifteen sectors, company records for the first five, and the event-token builder that feeds the quant engine. */
(function (root, factory) { if (typeof module === 'object' && module.exports) module.exports = factory(); else root.OrbitMVP = factory(); })(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const INDUSTRIES = ['Automotive', 'Energy', 'Banking', 'Pharma', 'Technology', 'FMCG & Food', 'Agriculture', 'Real Estate', 'Cement & Infra', 'Metals & Mining', 'Aviation & Travel', 'Telecom & Media', 'Retail & E-commerce', 'Consumer Durables', 'Gems & Jewellery'];
  const CATEGORIES = ['Supply disruption', 'Commodity shock', 'Regulation', 'Trade restriction', 'Interest-rate change', 'Geopolitical event', 'Demand shock'];
  // unit, dispersion of the realised move, precedent direction hit rate, horizon, title phrases [up, down]
  const VARS = {
    crude: { label: 'Crude oil price', unit: '%', sigmaE: 0.25, hit: 0.70, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['rises', 'falls'] },
    fuel_price: { label: 'Petrol, diesel and gas prices', unit: '%', sigmaE: 0.20, hit: 0.72, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rise', 'fall'] },
    rate: { label: 'Policy repo rate', unit: 'bps', sigmaE: 0.20, hit: 0.72, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    bank_rates: { label: 'Bank lending and deposit rates', unit: 'bps', sigmaE: 0.30, hit: 0.60, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    fed_rate: { label: 'US Federal Reserve rate', unit: 'bps', sigmaE: 0.20, hit: 0.60, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    steel: { label: 'Steel and iron ore prices', unit: '%', sigmaE: 0.30, hit: 0.70, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['rise', 'fall'] },
    metals: { label: 'Copper and aluminium prices', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['rise', 'fall'] },
    rare_earth: { label: 'Rare-earth magnets and critical minerals', unit: '%', sigmaE: 0.45, hit: 0.60, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['supply tightens', 'supply eases'] },
    chips: { label: 'Semiconductor and memory supply', unit: '%', sigmaE: 0.45, hit: 0.60, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['tightens', 'eases'] },
    us_tariff: { label: 'US tariffs on Indian exports', unit: 'pts', sigmaE: 0.35, hit: 0.65, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['raised', 'eased'] },
    trade_policy: { label: 'Trade agreements and duties', unit: 'pts', sigmaE: 0.40, hit: 0.65, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['tightened', 'eased'] },
    rupee: { label: 'Rupee against the dollar', unit: '%', sigmaE: 0.30, hit: 0.75, horizonQ: 1, horizonText: 'this quarter', phrase: ['strengthens', 'weakens'] },
    visa: { label: 'US work visas', unit: 'pts', sigmaE: 0.45, hit: 0.60, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['tightened', 'eased'] },
    drug_price: { label: 'Drug price control', unit: '%', sigmaE: 0.20, hit: 0.74, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    usfda: { label: 'US FDA action', unit: 'pts', sigmaE: 0.45, hit: 0.65, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['adverse action', 'approval'] },
    api: { label: 'Pharma intermediates and APIs', unit: '%', sigmaE: 0.35, hit: 0.65, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['supply tightens', 'supply eases'] },
    gst_auto: { label: 'GST on vehicles', unit: 'pts', sigmaE: 0.20, hit: 0.70, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    gst_other: { label: 'GST rate changes', unit: 'pts', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    ev_policy: { label: 'EV policy and incentives', unit: 'pts', sigmaE: 0.40, hit: 0.60, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['strengthened', 'withdrawn'] },
    ev_share: { label: 'EV sales share', unit: 'pts', sigmaE: 0.40, hit: 0.60, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['up', 'down'] },
    auto_demand: { label: 'Vehicle sales', unit: '%', sigmaE: 0.30, hit: 0.70, horizonQ: 1, horizonText: 'this quarter', phrase: ['up', 'down'] },
    it_demand: { label: 'IT services demand', unit: '%', sigmaE: 0.35, hit: 0.66, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['up', 'down'] },
    credit_growth: { label: 'Bank credit and deposit growth', unit: '%', sigmaE: 0.30, hit: 0.66, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['up', 'down'] },
    rbi_norms: { label: 'RBI banking rules', unit: 'pts', sigmaE: 0.45, hit: 0.60, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['tightened', 'eased'] },
    windfall_tax: { label: 'Windfall tax and fuel export duty', unit: '%', sigmaE: 0.30, hit: 0.70, horizonQ: 1, horizonText: 'this quarter', phrase: ['raised', 'cut'] },
    power_price: { label: 'Electricity tariffs and demand', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rise', 'fall'] },
    coal: { label: 'Coal price', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rises', 'falls'] },
    freight: { label: 'Shipping routes and freight', unit: '%', sigmaE: 0.40, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['disrupted', 'easing'] },
    geo_risk: { label: 'Geopolitical risk', unit: 'pts', sigmaE: 0.50, hit: 0.50, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['escalation', 'de-escalation'] },
    gold: { label: 'Gold and silver prices', unit: '%', sigmaE: 0.20, hit: 0.65, horizonQ: 1, horizonText: 'this quarter', phrase: ['rise', 'fall'] },
    travel_demand: { label: 'Air travel and airfares', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 1, horizonText: 'this quarter', phrase: ['up', 'down'] },
    housing_demand: { label: 'Housing sales and prices', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['up', 'down'] },
    cement: { label: 'Cement and building materials', unit: '%', sigmaE: 0.25, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rise', 'fall'] },
    infra_spend: { label: 'Government infrastructure spending', unit: '%', sigmaE: 0.35, hit: 0.65, horizonQ: 3, horizonText: '2 to 4 quarters', phrase: ['up', 'down'] },
    monsoon: { label: 'Monsoon and crop output', unit: '%', sigmaE: 0.35, hit: 0.60, horizonQ: 2, horizonText: '1 to 3 quarters', phrase: ['improves', 'weakens'] },
    fertiliser: { label: 'Fertiliser prices and subsidy', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rise', 'fall'] },
    farm_policy: { label: 'MSP and farm support', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    food_prices: { label: 'Food and edible oil prices', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['rise', 'fall'] },
    telecom_tariff: { label: 'Telecom tariffs and spectrum', unit: '%', sigmaE: 0.25, hit: 0.65, horizonQ: 2, horizonText: '1 to 2 quarters', phrase: ['raised', 'cut'] },
    retail_demand: { label: 'Retail and festive demand', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 1, horizonText: 'this quarter', phrase: ['up', 'down'] },
    durables_demand: { label: 'Consumer durables demand', unit: '%', sigmaE: 0.30, hit: 0.65, horizonQ: 1, horizonText: 'this quarter', phrase: ['up', 'down'] },
  };
  // Channel: variable, kind, name, share of revenue, sensitivity, pass-through, lag, hedge, substitution, signUp (+1 supportive when the variable rises), source, basis, beta override, sigmaC override
  const C = (variable, kind, name, share, sens, passThrough, lagQ, hedge, substitution, signUp, source, basis, beta, sigmaC, policyRisk) => ({ variable, kind, name, share, sens, passThrough, lagQ, hedge, substitution, signUp, source, basis, beta, sigmaC, policyRisk: policyRisk || 0 });
  const RAW = [
    { id: 'maruti', name: 'Maruti Suzuki', industry: 'Automotive', sector: 'Car manufacturer', margin: 0.12, asOf: '2026-06-30', desc: 'Largest car maker; steel is the biggest raw material and most buyers depend on car loans.', ch: [
      C('steel', 'cost', 'Steel and raw materials', 0.33, 0.5, 0.40, 1, 0.05, 0, -1, 'estimated', 'Raw materials 33% of revenue, steel about half of that'),
      C('metals', 'cost', 'Copper and aluminium content', 0.08, 0.6, 0.40, 1, 0, 0, -1, 'estimated', 'Non-ferrous content about 8% of revenue'),
      C('rate', 'demand', 'Car-loan financed demand', 0.80, 1, 0.30, 1, 0, 0, -1, 'estimated', '80% of sales financed; volumes fall about 1% per 50 bps', 4.0),
      C('bank_rates', 'demand', 'Car-loan EMIs', 0.80, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Bank-level rate changes reach EMIs directly', 2.0, 0.5),
      C('fuel_price', 'demand', 'Running-cost sensitive demand', 1.0, 1, 0.20, 1, 0, 0, -1, 'estimated', 'Entry-segment volumes slip about 0.1% per 1% fuel price rise', 0.2, 0.5),
      C('gst_auto', 'demand', 'GST on small cars', 1.0, 1, 0.10, 1, 0, 0, -1, 'estimated', 'A 5-point GST cut lifted small-car volumes about 8%', 2.5, 0.4),
      C('ev_share', 'demand', 'Petrol and hybrid mix', 1.0, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Late EV entrant; share loss on the margin', 0.15, 0.5),
      C('auto_demand', 'demand', 'Passenger vehicle demand', 1.0, 1, 0.10, 1, 0, 0, 1, 'estimated', 'Operating leverage about 2x on volume', 2.0, 0.35),
      C('rupee', 'cost', 'Imported content and royalty', 0.15, 1, 0.40, 1, 0.20, 0, 1, 'estimated', 'Imports and yen-linked royalty about 15% of revenue; a stronger rupee lowers them'),
      C('chips', 'cost', 'Semiconductor-dependent production', 0.05, 0.8, 0.20, 1, 0, 0, -1, 'estimated', 'Chip supply constrains output more than cost', null, 0.5),
    ] },
    { id: 'tata', name: 'Tata Motors', industry: 'Automotive', sector: 'Car, EV and truck maker', margin: 0.13, asOf: '2026-06-30', desc: 'Leads domestic EV sales; JLR earns in dollars and pounds; steel-heavy trucks.', ch: [
      C('steel', 'cost', 'Steel and raw materials', 0.35, 0.5, 0.45, 1, 0.10, 0, -1, 'estimated', 'Raw materials 35% of revenue'),
      C('metals', 'cost', 'Copper and aluminium content', 0.09, 0.6, 0.40, 1, 0, 0, -1, 'estimated', 'EV and body content'),
      C('rare_earth', 'cost', 'EV motor magnets', 0.03, 1.5, 0.20, 2, 0, 0.05, -1, 'estimated', 'Magnet supply constrains EV output', null, 0.5),
      C('ev_share', 'revenue', 'EV volume and mix', 0.15, 1, 0.70, 1, 0, 0, 1, 'estimated', 'About 70% of the incremental domestic EV market', 0.673, 0.323),
      C('ev_policy', 'revenue', 'EV incentives', 0.15, 1, 0.70, 2, 0, 0, 1, 'estimated', 'Incentives lift EV volumes', 0.5, 0.5),
      C('us_tariff', 'demand', 'JLR exports to the US', 0.25, 1, 0.30, 2, 0, 0, -1, 'estimated', 'JLR US sales about a quarter of group revenue', 0.15, 0.45),
      C('rupee', 'revenue', 'JLR revenue in foreign currency', 0.30, 1, 1.0, 1, 0.50, 0, -1, 'estimated', 'A stronger rupee cuts the rupee value of JLR earnings; half hedged'),
      C('auto_demand', 'demand', 'Domestic vehicle demand', 1.0, 1, 0.10, 1, 0, 0, 1, 'estimated', 'Operating leverage about 2x', 2.0, 0.35),
      C('rate', 'demand', 'Financed demand', 0.75, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Volumes fall about 0.8% per 50 bps', 3.2, 0.4),
      C('chips', 'cost', 'Semiconductor-dependent production', 0.05, 0.8, 0.20, 1, 0, 0, -1, 'estimated', 'Chip supply constrains output', null, 0.5),
      C('trade_policy', 'demand', 'Export access (FTA markets)', 0.30, 1, 0.30, 3, 0, 0, -1, 'estimated', 'FTA tariff cuts open EU and UK markets', 0.08, 0.5),
    ] },
    { id: 'mahindra', name: 'Mahindra & Mahindra', industry: 'Automotive', sector: 'SUV, tractor and EV maker', margin: 0.14, asOf: '2026-06-30', desc: 'SUV leader with a growing electric range; tractors follow rural demand.', ch: [
      C('steel', 'cost', 'Steel and raw materials', 0.32, 0.5, 0.45, 1, 0.05, 0, -1, 'estimated', 'Raw materials 32% of revenue'),
      C('rate', 'demand', 'Financed demand', 0.75, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Volumes fall about 0.8% per 50 bps', 3.2, 0.4),
      C('ev_share', 'revenue', 'Electric SUV mix', 0.08, 1, 0.70, 2, 0, 0, 1, 'estimated', 'Electric SUVs gaining share', 0.3, 0.5),
      C('ev_policy', 'revenue', 'EV incentives', 0.08, 1, 0.70, 2, 0, 0, 1, 'estimated', 'Incentives lift EV volumes', 0.3, 0.5),
      C('auto_demand', 'demand', 'SUV and tractor demand', 1.0, 1, 0.10, 1, 0, 0, 1, 'estimated', 'Operating leverage about 2x', 2.0, 0.35),
      C('rare_earth', 'cost', 'EV motor magnets', 0.02, 1.5, 0.20, 2, 0, 0.05, -1, 'estimated', 'Magnet supply constrains EV output', null, 0.5),
      C('gst_auto', 'demand', 'GST on vehicles', 1.0, 1, 0.10, 1, 0, 0, -1, 'estimated', 'GST cuts lift SUV volumes', 1.8, 0.4),
    ] },
    { id: 'hero', name: 'Hero MotoCorp', industry: 'Automotive', sector: 'Two-wheeler manufacturer', margin: 0.14, asOf: '2026-06-30', desc: 'Largest two-wheeler maker; exposed to steel, fuel prices and the shift to electric scooters.', ch: [
      C('steel', 'cost', 'Steel and raw materials', 0.30, 0.5, 0.26, 1, 0, 0, -1, 'estimated', 'Raw materials 30% of revenue; price revisions lag a quarter', 0.223, 0.347),
      C('ev_share', 'demand', 'Petrol two-wheeler demand', 0.90, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Electric scooters take share from entry petrol models', 0.184, 0.511),
      C('fuel_price', 'demand', 'Running-cost sensitive demand', 1.0, 1, 0.20, 1, 0, 0, -1, 'estimated', 'Entry two-wheeler volumes slip about 0.15% per 1% fuel price rise', 0.3, 0.5),
      C('auto_demand', 'demand', 'Two-wheeler demand', 1.0, 1, 0.10, 1, 0, 0, 1, 'estimated', 'Operating leverage about 2x', 2.0, 0.35),
      C('gst_auto', 'demand', 'GST on two-wheelers', 1.0, 1, 0.10, 1, 0, 0, -1, 'estimated', 'GST cuts lift entry volumes', 2.0, 0.4),
      C('rate', 'demand', 'Financed demand', 0.60, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Volumes fall about 0.5% per 50 bps', 2.0, 0.4),
    ] },
    { id: 'bajaj', name: 'Bajaj Auto', industry: 'Automotive', sector: 'Two- and three-wheeler maker', margin: 0.20, asOf: '2026-06-30', desc: 'Exports about a third of output; three-wheelers and the Chetak electric scooter.', ch: [
      C('steel', 'cost', 'Steel and raw materials', 0.28, 0.5, 0.40, 1, 0, 0, -1, 'estimated', 'Raw materials 28% of revenue'),
      C('rupee', 'revenue', 'Export revenue', 0.33, 1, 1.0, 1, 0.50, 0, -1, 'estimated', 'A third of revenue in foreign currency; half hedged'),
      C('us_tariff', 'demand', 'Export markets', 0.33, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Small direct US exposure', 0.05, 0.5),
      C('trade_policy', 'demand', 'Export access', 0.33, 1, 0.30, 3, 0, 0, -1, 'estimated', 'FTA tariff cuts open new markets', 0.08, 0.5),
      C('auto_demand', 'demand', 'Two-wheeler demand', 1.0, 1, 0.10, 1, 0, 0, 1, 'estimated', 'Operating leverage about 1.6x', 1.6, 0.35),
      C('ev_share', 'revenue', 'Chetak electric scooters', 0.08, 1, 0.70, 2, 0, 0, 1, 'estimated', 'Chetak gains with the electric shift', 0.2, 0.5),
      C('gst_auto', 'demand', 'GST on two-wheelers', 1.0, 1, 0.10, 1, 0, 0, -1, 'estimated', 'GST cuts lift entry volumes', 1.5, 0.4),
    ] },
    { id: 'ongc', name: 'ONGC', industry: 'Energy', sector: 'Oil and gas producer', margin: 0.45, asOf: '2026-06-30', desc: 'Realisations track crude; a windfall levy caps the upside; fuel demand shifts matter over years.', ch: [
      C('crude', 'revenue', 'Crude realisations', 0.75, 1, 0.82, 1, 0.12, 0, 1, 'disclosed', 'Company sensitivity table: EBITDA per $1/bbl; 82% captured after the windfall levy', 0.714, 0.421, 0.40),
      C('windfall_tax', 'demand', 'Windfall levy on crude', 0.75, 1, 0.10, 1, 0, 0, -1, 'estimated', 'A 20% rise in the levy rate takes about 3% of EBITDA', 0.15, 0.4),
      C('rupee', 'revenue', 'Dollar-linked realisations', 0.75, 1, 0.82, 1, 0.12, 0, -1, 'estimated', 'Crude is priced in dollars; a stronger rupee cuts rupee realisations'),
      C('ev_share', 'demand', 'Domestic fuel demand', 0.75, 1, 0.20, 2, 0.12, 0, -1, 'estimated', 'Petrol demand growth slows about 0.5 pp per EV share point', 0.299, 0.549),
      C('geo_risk', 'demand', 'Supply risk premium', 0.75, 1, 0.50, 1, 0.12, 0, 1, 'estimated', 'Escalation lifts the risk premium in crude', 0.02, 0.6),
    ] },
    { id: 'oilindia', name: 'Oil India', industry: 'Energy', sector: 'Oil and gas producer', margin: 0.42, asOf: '2026-06-30', desc: 'Oil and gas producer in the north-east; realisations track crude.', ch: [
      C('crude', 'revenue', 'Crude realisations', 0.70, 1, 0.80, 1, 0.10, 0, 1, 'estimated', 'Realisations 70% of revenue; windfall levy applies above a threshold', 0.520, 0.402, 0.30),
      C('windfall_tax', 'demand', 'Windfall levy on crude', 0.70, 1, 0.10, 1, 0, 0, -1, 'estimated', 'Levy takes a share of realisations above the threshold', 0.12, 0.4),
      C('rupee', 'revenue', 'Dollar-linked realisations', 0.70, 1, 0.80, 1, 0.10, 0, -1, 'estimated', 'Crude is priced in dollars'),
    ] },
    { id: 'ioc', name: 'Indian Oil', industry: 'Energy', sector: 'Oil refining and marketing', margin: 0.08, asOf: '2026-06-30', desc: 'Refiner and fuel retailer; crude is the input and retail prices lag.', ch: [
      C('crude', 'cost', 'Crude input', 0.85, 1, 0.30, 1, 0.08, 0, -1, 'estimated', 'Retail price lag; marketing margin absorbs the first weeks', 0.481, 0.228, 0.2),
      C('fuel_price', 'revenue', 'Retail fuel prices', 0.90, 1, 0.90, 1, 0, 0, 1, 'estimated', 'A 1% retail price change moves marketing margin about 4% of EBITDA on a thin base', 4.0, 0.5),
      C('rupee', 'cost', 'Dollar-priced crude imports', 0.85, 1, 0.60, 1, 0.20, 0, 1, 'estimated', 'A stronger rupee lowers the rupee cost of crude', null, 0.5),
      C('windfall_tax', 'demand', 'Export duty on fuels', 0.10, 1, 0.50, 1, 0, 0, -1, 'estimated', 'Small export book', 0.03, 0.5),
      C('freight', 'cost', 'Crude shipping', 0.03, 1, 0.50, 1, 0, 0, -1, 'estimated', 'Tanker rates a small share of landed cost', null, 0.5),
      C('geo_risk', 'demand', 'Supply and price risk', 0.85, 1, 0.50, 1, 0, 0, -1, 'estimated', 'Escalation raises crude and squeezes margins before retail prices move', 0.015, 0.6),
    ] },
    { id: 'bpcl', name: 'BPCL', industry: 'Energy', sector: 'Oil refining and marketing', margin: 0.09, asOf: '2026-06-30', desc: 'Refiner and fuel retailer with a larger hedge book than peers.', ch: [
      C('crude', 'cost', 'Crude input', 0.84, 1, 0.35, 1, 0.14, 0, -1, 'estimated', 'Retail price lag; 14% of crude purchases hedged', 0.441, 0.238, 0.2),
      C('fuel_price', 'revenue', 'Retail fuel prices', 0.90, 1, 0.90, 1, 0, 0, 1, 'estimated', 'A 1% retail price change moves marketing margin about 4% of EBITDA', 3.8, 0.5),
      C('rupee', 'cost', 'Dollar-priced crude imports', 0.84, 1, 0.60, 1, 0.25, 0, 1, 'estimated', 'A stronger rupee lowers the rupee cost of crude', null, 0.5),
      C('freight', 'cost', 'Crude shipping', 0.03, 1, 0.50, 1, 0, 0, -1, 'estimated', 'Tanker rates a small share of landed cost', null, 0.5),
      C('geo_risk', 'demand', 'Supply and price risk', 0.84, 1, 0.50, 1, 0, 0, -1, 'estimated', 'Escalation raises crude before retail prices move', 0.015, 0.6),
    ] },
    { id: 'coalindia', name: 'Coal India', industry: 'Energy', sector: 'Coal producer', margin: 0.30, asOf: '2026-06-30', desc: 'Supplies most of the coal burnt by power plants; e-auction prices follow demand.', ch: [
      C('coal', 'revenue', 'E-auction and notified prices', 0.90, 1, 0.80, 1, 0, 0, 1, 'estimated', 'About 20% of volume sold at e-auction prices that track the market', 1.2, 0.4),
      C('power_price', 'demand', 'Power demand', 0.90, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Coal offtake follows power demand', 0.8, 0.4),
      C('trade_policy', 'demand', 'Import competition', 0.90, 1, 0.50, 2, 0, 0, 1, 'estimated', 'Import duties on coal support domestic offtake', 0.03, 0.5),
    ] },
    { id: 'ntpc', name: 'NTPC', industry: 'Energy', sector: 'Power generator', margin: 0.30, asOf: '2026-06-30', desc: 'Largest power generator; regulated tariffs pass fuel cost through with a lag.', ch: [
      C('coal', 'cost', 'Coal fuel cost', 0.55, 1, 0.90, 1, 0, 0, -1, 'estimated', 'Regulated tariffs pass most fuel cost through'),
      C('power_price', 'revenue', 'Tariff revisions', 1.0, 1, 0.30, 2, 0, 0, 1, 'estimated', 'Regulated return; only a share of tariff moves reaches earnings', 1.0, 0.4),
      C('rate', 'finance', 'Floating-rate debt', 0.60, 1, 0.50, 2, 0.40, 0, -1, 'estimated', 'Leverage of about 0.6x revenue; part fixed', 2.0, 0.45),
    ] },
    { id: 'hdfc', name: 'HDFC Bank', industry: 'Banking', sector: 'Private sector bank', margin: 0.55, asOf: '2026-06-30', desc: 'Net interest margin widens when policy rates rise; a large treasury book marks to market.', ch: [
      C('rate', 'finance', 'Net interest margin', 0.80, 1, 0.70, 1, 0, 0, 1, 'disclosed', 'Interest-rate sensitivity table: NII +5.7% per 100 bps; 70% of the policy move reaches the book', 8.081, 0.402),
      C('bank_rates', 'finance', 'Loan repricing', 0.80, 1, 0.80, 1, 0, 0, 1, 'estimated', 'Own lending-rate moves reach the book directly', 2.0, 0.5),
      C('fed_rate', 'treasury', 'Treasury book (AFS)', 0.10, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Higher global yields mark the AFS book down', 1.0, 0.5),
      C('credit_growth', 'demand', 'Loan book growth', 0.80, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Earnings scale with the loan book', 1.2, 0.4),
      C('rbi_norms', 'demand', 'Regulatory cost', 0.80, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Tighter norms raise provisioning or capital cost', 0.05, 0.6),
    ] },
    { id: 'icici', name: 'ICICI Bank', industry: 'Banking', sector: 'Private sector bank', margin: 0.55, asOf: '2026-06-30', desc: 'Large floating-rate loan book; margin follows the policy rate quickly.', ch: [
      C('rate', 'finance', 'Net interest margin', 0.80, 1, 0.75, 1, 0, 0, 1, 'disclosed', 'Interest-rate sensitivity table; 75% of the policy move reaches the book', 6.788, 0.402),
      C('bank_rates', 'finance', 'Loan repricing', 0.80, 1, 0.80, 1, 0, 0, 1, 'estimated', 'Own lending-rate moves reach the book directly', 2.0, 0.5),
      C('fed_rate', 'treasury', 'Treasury book (AFS)', 0.10, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Higher global yields mark the AFS book down', 1.0, 0.5),
      C('credit_growth', 'demand', 'Loan book growth', 0.80, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Earnings scale with the loan book', 1.2, 0.4),
      C('rbi_norms', 'demand', 'Regulatory cost', 0.80, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Tighter norms raise provisioning or capital cost', 0.05, 0.6),
    ] },
    { id: 'sbi', name: 'State Bank of India', industry: 'Banking', sector: 'Public sector bank', margin: 0.50, asOf: '2026-06-30', desc: 'Largest bank; deposit franchise reprices slowly, large government bond holdings.', ch: [
      C('rate', 'finance', 'Net interest margin', 0.80, 1, 0.55, 1, 0, 0, 1, 'disclosed', 'Interest-rate sensitivity table; 55% of the policy move reaches the book', 6.171, 0.402),
      C('bank_rates', 'finance', 'Loan repricing', 0.80, 1, 0.80, 1, 0, 0, 1, 'estimated', 'Own lending-rate moves reach the book directly', 1.8, 0.5),
      C('fed_rate', 'treasury', 'Treasury book (AFS)', 0.15, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Larger bond book marks down when yields rise', 1.4, 0.5),
      C('credit_growth', 'demand', 'Loan book growth', 0.80, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Earnings scale with the loan book', 1.1, 0.4),
      C('rbi_norms', 'demand', 'Regulatory cost', 0.80, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Tighter norms raise provisioning or capital cost', 0.06, 0.6),
    ] },
    { id: 'axis', name: 'Axis Bank', industry: 'Banking', sector: 'Private sector bank', margin: 0.52, asOf: '2026-06-30', desc: 'Corporate and retail lending; margin follows the policy rate.', ch: [
      C('rate', 'finance', 'Net interest margin', 0.80, 1, 0.70, 1, 0, 0, 1, 'disclosed', 'Interest-rate sensitivity table; 70% of the policy move reaches the book', 6.465, 0.402),
      C('bank_rates', 'finance', 'Loan repricing', 0.80, 1, 0.80, 1, 0, 0, 1, 'estimated', 'Own lending-rate moves reach the book directly', 2.0, 0.5),
      C('fed_rate', 'treasury', 'Treasury book (AFS)', 0.10, 1, 0.30, 1, 0, 0, -1, 'estimated', 'Higher global yields mark the AFS book down', 1.0, 0.5),
      C('credit_growth', 'demand', 'Loan book growth', 0.80, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Earnings scale with the loan book', 1.2, 0.4),
      C('rbi_norms', 'demand', 'Regulatory cost', 0.80, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Tighter norms raise provisioning or capital cost', 0.05, 0.6),
    ] },
    { id: 'sun', name: 'Sun Pharmaceutical', industry: 'Pharma', sector: 'Drug maker', margin: 0.28, asOf: '2026-06-30', desc: 'Largest drug maker; imports intermediates, sells price-controlled essential drugs, a third of sales in the US.', ch: [
      C('api', 'cost', 'Imported intermediates', 0.22, 1, 0.30, 1, 0.10, 0, -1, 'estimated', 'Intermediates 22% of revenue', 0.299, 0.312),
      C('drug_price', 'demand', 'Price-controlled portfolio', 0.25, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Essential drugs about 25% of domestic revenue; mix shift offsets 20%', 0.331, 0.391),
      C('usfda', 'demand', 'US plant compliance', 0.30, 1, 0.20, 2, 0, 0, -1, 'estimated', 'An import alert on a key plant costs several percent of US sales', 0.25, 0.6),
      C('us_tariff', 'demand', 'US generics exports', 0.30, 1, 0.30, 2, 0, 0, -1, 'estimated', 'About 30% of sales in the US; generics partly exempt', 0.15, 0.5),
      C('rupee', 'revenue', 'Export revenue', 0.60, 1, 1.0, 1, 0.40, 0, -1, 'estimated', '60% of revenue in foreign currency; 40% hedged'),
      C('rate', 'finance', 'Floating-rate debt', 0.05, 1, 0.20, 1, 0, 0, -1, 'estimated', 'Net debt small relative to EBITDA', 1.732, 0.683),
    ] },
    { id: 'divis', name: "Divi's Laboratories", industry: 'Pharma', sector: 'API and intermediate maker', margin: 0.33, asOf: '2026-06-30', desc: 'Makes active ingredients in India; gains when imported supply is restricted; exports most output.', ch: [
      C('api', 'revenue', 'Domestic intermediate sales', 0.60, 1, 0.75, 1, 0, 0, 1, 'estimated', 'Domestic API pricing follows import parity', 0.377, 0.312),
      C('rupee', 'revenue', 'Export revenue', 0.85, 1, 1.0, 1, 0.30, 0, -1, 'estimated', '85% of revenue in foreign currency; 30% hedged'),
      C('us_tariff', 'demand', 'US exports', 0.40, 1, 0.30, 2, 0, 0, -1, 'estimated', 'APIs largely exempt but customers are exposed', 0.1, 0.5),
      C('usfda', 'demand', 'US plant compliance', 0.40, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Plant inspections gate US supply', 0.2, 0.6),
    ] },
    { id: 'cipla', name: 'Cipla', industry: 'Pharma', sector: 'Drug maker', margin: 0.25, asOf: '2026-06-30', desc: 'Strong domestic franchise with a large price-controlled respiratory portfolio; a quarter of sales in the US.', ch: [
      C('api', 'cost', 'Imported intermediates', 0.25, 1, 0.30, 1, 0.05, 0, -1, 'estimated', 'Intermediates 25% of revenue'),
      C('drug_price', 'demand', 'Price-controlled portfolio', 0.40, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Larger domestic share than peers', 0.4, 0.4),
      C('usfda', 'demand', 'US plant compliance', 0.25, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Goa and Indore plants under inspection cycles', 0.2, 0.6),
      C('us_tariff', 'demand', 'US generics exports', 0.25, 1, 0.30, 2, 0, 0, -1, 'estimated', 'About a quarter of sales in the US', 0.1, 0.5),
      C('rupee', 'revenue', 'Export revenue', 0.45, 1, 1.0, 1, 0.30, 0, -1, 'estimated', '45% of revenue in foreign currency; 30% hedged'),
    ] },
    { id: 'drreddy', name: "Dr Reddy's", industry: 'Pharma', sector: 'Drug maker', margin: 0.26, asOf: '2026-06-30', desc: 'Nearly half of sales in the US; exposed to FDA actions and US trade policy.', ch: [
      C('api', 'cost', 'Imported intermediates', 0.20, 1, 0.30, 1, 0.05, 0, -1, 'estimated', 'Intermediates 20% of revenue'),
      C('drug_price', 'demand', 'Price-controlled portfolio', 0.20, 1, 0.20, 1, 0, 0, 1, 'estimated', 'Smaller domestic share', 0.2, 0.4),
      C('usfda', 'demand', 'US plant compliance', 0.45, 1, 0.20, 2, 0, 0, -1, 'estimated', 'US is the largest market; plant actions bite', 0.3, 0.6),
      C('us_tariff', 'demand', 'US generics exports', 0.45, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Nearly half of sales in the US', 0.25, 0.5),
      C('rupee', 'revenue', 'Export revenue', 0.55, 1, 1.0, 1, 0.40, 0, -1, 'estimated', '55% of revenue in foreign currency; 40% hedged'),
    ] },
    { id: 'tcs', name: 'TCS', industry: 'Technology', sector: 'IT services', margin: 0.26, asOf: '2026-06-30', desc: 'Largest IT services exporter; revenue follows enterprise technology budgets and the dollar.', ch: [
      C('it_demand', 'demand', 'Enterprise services demand', 0.95, 1, 0.10, 2, 0, 0, 1, 'estimated', 'Revenue elasticity to client budgets about 0.4 with a two-quarter lag', 0.3, 0.33),
      C('visa', 'demand', 'US onsite delivery', 0.50, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Visa costs and limits raise onsite cost; offshore shift offsets 30%', 0.1, 0.5),
      C('rupee', 'revenue', 'Dollar and euro revenue', 0.90, 1, 1.0, 1, 0.50, 0, -1, 'estimated', '90% of revenue in foreign currency; about half hedged'),
      C('fed_rate', 'demand', 'US client spending', 0.55, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Higher US rates slow discretionary tech spending', 0.3, 0.6),
    ] },
    { id: 'infosys', name: 'Infosys', industry: 'Technology', sector: 'IT services', margin: 0.24, asOf: '2026-06-30', desc: 'Second-largest IT exporter; large financial-services client base in the US and Europe.', ch: [
      C('it_demand', 'demand', 'Enterprise services demand', 0.95, 1, 0.10, 2, 0, 0, 1, 'estimated', 'Revenue elasticity to client budgets about 0.4', 0.3, 0.33),
      C('visa', 'demand', 'US onsite delivery', 0.55, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Higher onsite mix than peers', 0.12, 0.5),
      C('rupee', 'revenue', 'Dollar and euro revenue', 0.95, 1, 1.0, 1, 0.50, 0, -1, 'estimated', '95% of revenue in foreign currency; about half hedged'),
      C('fed_rate', 'demand', 'US client spending', 0.60, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Higher US rates slow discretionary tech spending', 0.3, 0.6),
    ] },
    { id: 'wipro', name: 'Wipro', industry: 'Technology', sector: 'IT services', margin: 0.20, asOf: '2026-06-30', desc: 'IT services exporter with a thinner margin; more sensitive to demand and visa costs.', ch: [
      C('it_demand', 'demand', 'Enterprise services demand', 0.95, 1, 0.10, 2, 0, 0, 1, 'estimated', 'Thinner margin amplifies the percentage effect', 0.4, 0.33),
      C('visa', 'demand', 'US onsite delivery', 0.55, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Visa costs weigh more on a thin margin', 0.14, 0.5),
      C('rupee', 'revenue', 'Dollar and euro revenue', 0.95, 1, 1.0, 1, 0.50, 0, -1, 'estimated', '95% of revenue in foreign currency; about half hedged'),
      C('fed_rate', 'demand', 'US client spending', 0.60, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Higher US rates slow discretionary tech spending', 0.35, 0.6),
    ] },
    { id: 'hcl', name: 'HCLTech', industry: 'Technology', sector: 'IT services', margin: 0.22, asOf: '2026-06-30', desc: 'IT and engineering services exporter with a large software products business.', ch: [
      C('it_demand', 'demand', 'Enterprise services demand', 0.95, 1, 0.10, 2, 0, 0, 1, 'estimated', 'Revenue elasticity to client budgets about 0.4', 0.33, 0.33),
      C('visa', 'demand', 'US onsite delivery', 0.50, 1, 0.30, 2, 0, 0, -1, 'estimated', 'Visa costs and limits raise onsite cost', 0.1, 0.5),
      C('rupee', 'revenue', 'Dollar and euro revenue', 0.95, 1, 1.0, 1, 0.50, 0, -1, 'estimated', '95% of revenue in foreign currency; about half hedged'),
      C('fed_rate', 'demand', 'US client spending', 0.60, 1, 0.20, 2, 0, 0, -1, 'estimated', 'Higher US rates slow discretionary tech spending', 0.3, 0.6),
    ] },
  ];
  const r3 = x => Math.round(x * 1000) / 1000;
  const COMPANIES = RAW.map(c => ({ id: c.id, name: c.name, industry: c.industry, sector: c.sector, margin: c.margin, asOf: c.asOf, desc: c.desc, channels: c.ch.map(h => ({ variable: h.variable, kind: h.kind, name: h.name, share: h.share, beta: h.beta != null ? h.beta : r3(h.share * h.sens / c.margin), sigmaC: h.sigmaC != null ? h.sigmaC : (h.source === 'disclosed' ? 0.25 : 0.35), passThrough: h.passThrough, lagQ: h.lagQ, hedge: h.hedge, substitution: h.substitution, signUp: h.signUp, policyRisk: h.policyRisk, source: h.source, basis: h.basis })) }));
  const companyById = id => COMPANIES.find(c => c.id === id);
  const fmtMag = (v, unit) => unit === 'bps' ? Math.round(v) + ' bps' : unit === 'pts' ? (Math.round(v * 10) / 10) + ' pts' : (Math.round(v * 10) / 10) + '%';
  function titleOf(e) {
    const V = VARS[e.var]; const up = e.dir > 0; const phrase = V.phrase[up ? 0 : 1];
    const mag = e.extracted ? ' ' + fmtMag(e.mag, e.unit) : '';
    const topic = e.topic && !['relief', ''].includes(e.topic) ? ', ' + e.topic : '';
    const suffix = e.nFacts === 0 ? ' (expected)' : '';
    if (e.var === 'geo_risk') return 'Geopolitical risk' + topic + ': ' + phrase + suffix;
    if (e.var === 'freight') return 'Shipping routes' + topic + ': ' + phrase + suffix;
    return V.label + ' ' + phrase + mag + suffix;
  }
  function tokenOf(e) {
    const V = VARS[e.var]; const facts = e.reports.filter(r => !r.outlook).length;
    const sigmaE = e.extracted ? V.sigmaE : Math.min(0.8, V.sigmaE + 0.25);
    return { id: e.id, title: titleOf(e), keys: [], tags: e.cats, date: e.last.slice(0, 10), horizonQ: V.horizonQ, horizonText: V.horizonText,
      variable: { name: e.var, label: V.label, unit: V.unit, magnitude: e.dir * e.mag }, sigmaE, hit: V.hit, precedents: [],
      sources: e.reports.map(r => ({ src: 'Jagran business desk, ' + r.type + ', ' + r.date.slice(0, 10), cred: r.outlook ? 0.6 : 0.85, type: r.outlook ? 'PREDICTION' : 'FACT', claim: 'event', text: r.headline })), facts };
  }
  const exposedCompanies = e => COMPANIES.filter(c => c.channels.some(h => h.variable === e.var));
  return { INDUSTRIES, CATEGORIES, VARS, COMPANIES, companyById, titleOf, tokenOf, exposedCompanies, fmtMag };
});
