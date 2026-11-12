#!/usr/bin/env node
/*
 * Monte Carlo blackjack simulator.
 *   node sim.js                -> runs all scenarios, writes results.json + calibration.js
 *   node sim.js --rounds 2e6   -> fewer rounds per scenario (faster)
 * Uses every CPU core (worker_threads). The strategy table comes from engine.js.
 */
'use strict';
const { Worker, isMainThread, parentPort, workerData } = require('worker_threads');
const os = require('os');
const fs = require('fs');
const path = require('path');
const BJ = require('./engine.js');

// ------------------------------------------------------------------ RNG (sfc32)
function rng(seed) {
  let a = 0x9e3779b9 ^ seed, b = 0x243f6a88 + seed * 7, c = 0xb7e15162 ^ (seed << 3), d = 1;
  return function () {
    a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
    const t = (a + b | 0) + d | 0; d = d + 1 | 0;
    a = b ^ b >>> 9; b = c + (c << 3) | 0; c = (c << 21 | c >>> 11); c = c + t | 0;
    return (t >>> 0) / 4294967296;
  };
}

// ------------------------------------------------------------------ Strategy encoding
const A = { S: 0, H: 1, D: 2, P: 3, R: 4 };
function encodeTable(st) {
  // arrays indexed [up*32 + total]; values are codes 'S','H','D','Ds','R','Rs'
  const hard = new Array(11 * 32), soft = new Array(11 * 32), pair = new Array(11 * 11).fill(false);
  for (const up of BJ.UPS) {
    for (let t = 4; t <= 21; t++) hard[up * 32 + t] = st.hard[up][t] || (t >= 17 ? 'S' : 'H');
    for (let t = 12; t <= 21; t++) soft[up * 32 + t] = st.soft[up][t] || 'S';
    for (let r = 1; r <= 10; r++) pair[up * 11 + r] = st.pair[up][r];
  }
  for (const up of BJ.UPS) for (let t = 22; t < 32; t++) { hard[up * 32 + t] = 'S'; soft[up * 32 + t] = 'S'; }
  return { hard, soft, pair };
}

function buildIndex() {
  const m = new Map();
  for (const [type, total, up, idx, act] of BJ.INDEX_PLAYS) m.set(type + total + '_' + up, [idx, act]);
  return m;
}

// ------------------------------------------------------------------ One scenario on one worker
function runScenario(sc, rounds, seed) {
  const R = BJ.rulesWith(sc.rules);
  const T = encodeTable(BJ.generateStrategy(R));
  const IDX = buildIndex();
  const rand = rng(seed);
  const nCards = 52 * R.decks;
  const shoe = new Int8Array(nCards);
  { let k = 0; for (let r = 1; r <= 10; r++) { const n = (r === 10 ? 16 : 4) * R.decks; for (let i = 0; i < n; i++) shoe[k++] = r; } }
  const cut = Math.floor(nCards * R.penetration);
  let pos = nCards; // force shuffle
  let rc = 0;
  const seen = []; // cards revealed during the round, counted at the end of the round
  function shuffle() {
    for (let i = nCards - 1; i > 0; i--) { const j = (rand() * (i + 1)) | 0; const t = shoe[i]; shoe[i] = shoe[j]; shoe[j] = t; }
    pos = 0; rc = 0;
  }
  function draw() { const c = shoe[pos++]; seen.push(c); return c; }

  const counting = !!sc.count;
  const useIdx = !!sc.indices;
  function tcOf() { const decksLeft = (nCards - pos) / 52; return Math.floor(rc / Math.max(decksLeft, 0.25)); }

  function decide(hard, ace, n, isPair, pr, up, nHands, afterSplit, tc) {
    const t = BJ.effTotal(hard, ace);
    const soft = ace && hard + 10 <= 21;
    const canDbl = n === 2 && (!afterSplit || R.das) && (R.doubleAny || (!soft && t >= 9 && t <= 11));
    const canSur = n === 2 && !afterSplit && R.surrender;
    if (isPair && nHands < R.maxHands) {
      let split = T.pair[up * 11 + pr];
      if (useIdx && pr === 10) { const ix = IDX.get('pair10_' + up); if (ix) split = tc >= ix[0]; }
      if (split) return A.P;
    }
    if (canSur && useIdx && !soft) {
      for (const [tt, uu, ii] of BJ.SURR_INDEX) if (tt === t && uu === up && tc >= ii) return A.R;
    }
    let c = soft ? T.soft[up * 32 + t] : T.hard[up * 32 + t];
    if (useIdx && !soft) {
      const ix = IDX.get('hard' + t + '_' + up);
      if (ix) {
        const [ii, act] = ix;
        if (act === 'S') c = tc >= ii ? 'S' : 'H';
        else if (act === 'D') c = tc >= ii ? 'D' : (c === 'D' ? 'H' : c);
      }
    }
    switch (c) {
      case 'S': return A.S;
      case 'H': return A.H;
      case 'D': return canDbl ? A.D : A.H;
      case 'Ds': return canDbl ? A.D : A.S;
      case 'R': return canSur ? A.R : A.H;
      case 'Rs': return canSur ? A.R : A.S;
    }
    return A.S;
  }

  // plays one seat; returns array of hands {hard, ace, bet, done, bust, sur, natural}
  function playSeat(c1, c2, up, bet, tc) {
    const hands = [{ hard: c1 + c2, ace: c1 === 1 || c2 === 1, n: 2, bet, cards0: c1, pair: c1 === c2, afterSplit: false, splitAces: false }];
    for (let h = 0; h < hands.length; h++) {
      const H = hands[h];
      if (H.splitAces) continue;
      for (;;) {
        const t = BJ.effTotal(H.hard, H.ace);
        if (t >= 21) break;
        const a = decide(H.hard, H.ace, H.n, H.pair && H.n === 2, H.cards0, up, hands.length, H.afterSplit, tc);
        if (a === A.S) break;
        if (a === A.R) { H.sur = true; break; }
        if (a === A.P) {
          const r = H.cards0;
          const nh = { hard: r, ace: r === 1, n: 1, bet: H.bet, cards0: r, pair: false, afterSplit: true, splitAces: r === 1 };
          H.hard = r; H.ace = r === 1; H.n = 1; H.afterSplit = true; H.splitAces = r === 1;
          hands.push(nh);
          for (const X of [H, nh]) { const c = draw(); X.hard += c; X.ace = X.ace || c === 1; X.n = 2; X.pair = c === r; }
          if (H.splitAces) break;
          continue;
        }
        const c = draw(); H.hard += c; H.ace = H.ace || c === 1; H.n++;
        if (a === A.D) { H.bet *= 2; H.dbl = true; break; }
      }
    }
    return hands;
  }

  function dealerPlay(hard, ace) {
    for (;;) {
      const t = BJ.effTotal(hard, ace);
      if (t > 17 || (t === 17 && !(R.h17 && ace && hard + 10 === 17))) return t;
      if (t < 17 || (t === 17)) { const c = draw(); hard += c; ace = ace || c === 1; }
    }
  }

  // betting
  function betFor(tc) {
    if (!counting) return 1;
    const sp = sc.spread; // array of [minTC, units] ascending
    if (sc.wongOut !== undefined && tc < sc.wongOut) return 0;
    let b = sp[0][1];
    for (const [m, u] of sp) if (tc >= m) b = u;
    return b;
  }

  const others = sc.others ?? 3;
  let played = 0, observed = 0, sum = 0, sumSq = 0, wagered = 0, initial = 0;
  const byTC = {}; // flat-bet EV per TC bucket (for calibration)
  let bankroll = sc.bankroll || 0, minBank = 0, peak = 0, maxDD = 0;
  let ruined = false;
  const mart = sc.martingale ? { unit: 1, cur: 1, maxBet: sc.martingale.maxBet, bank: sc.martingale.bank, target: sc.martingale.target, sessions: 0, busts: 0, wins: 0, profit: 0, winSum: 0, rounds: 0, cash: sc.martingale.bank } : null;

  shuffle();
  for (let round = 0; round < rounds; round++) {
    if (pos >= cut) shuffle();
    seen.length = 0;
    const tc = tcOf();
    let bet = betFor(tc);
    if (mart) bet = Math.min(mart.cur, mart.cash);
    observed++;
    // deal: our seat (if betting), others, dealer
    const seats = [];
    if (bet > 0) seats.push({ me: true, c1: draw(), c2: 0 });
    for (let i = 0; i < others; i++) seats.push({ me: false, c1: draw(), c2: 0 });
    const up = draw();
    for (const s of seats) s.c2 = draw();
    const hole = shoe[pos++]; // not counted until revealed
    const dealerBJ = BJ.effTotal(up + hole, up === 1 || hole === 1) === 21;

    let net = 0;
    const me = seats.find(s => s.me);
    let insurance = 0;
    if (me && up === 1 && counting && tc >= 3) insurance = bet / 2;

    if (R.peek && dealerBJ) {
      if (me) {
        const nat = BJ.effTotal(me.c1 + me.c2, me.c1 === 1 || me.c2 === 1) === 21;
        net = (nat ? 0 : -bet) + insurance * 2;
      }
      seen.push(hole);
    } else {
      if (me && insurance) net -= insurance; // insurance lost (peek), or settled below for ENHC
      const results = [];
      for (const s of seats) {
        const nat = BJ.effTotal(s.c1 + s.c2, s.c1 === 1 || s.c2 === 1) === 21;
        if (nat) { results.push({ s, nat: true }); continue; }
        results.push({ s, hands: playSeat(s.c1, s.c2, up, s.me ? bet : 1, tc) });
      }
      seen.push(hole);
      let dTot;
      if (dealerBJ) dTot = 99; // ENHC dealer blackjack
      else {
        const anyLive = results.some(r => r.hands && r.hands.some(h => !h.sur && BJ.effTotal(h.hard, h.ace) <= 21));
        dTot = anyLive ? dealerPlay(up + hole, up === 1 || hole === 1) : 0;
      }
      if (me) {
        const r = results.find(x => x.s.me);
        if (dealerBJ && insurance) net += insurance * 3; // ENHC insurance wins (stake returned + 2:1)
        if (r.nat) net += dealerBJ ? 0 : bet * R.bjPays;
        else for (const h of r.hands) {
          const t = BJ.effTotal(h.hard, h.ace);
          if (h.sur) { net -= h.bet / 2; continue; }
          if (dealerBJ) { net -= R.enhcLoseAll ? h.bet : (r.hands.indexOf(h) === 0 ? bet : 0); continue; }
          if (t > 21) net -= h.bet;
          else if (dTot > 21 || t > dTot) net += h.bet;
          else if (t < dTot) net -= h.bet;
        }
      }
    }
    // count everything revealed this round
    for (let i = 0; i < seen.length; i++) rc += BJ.hiLo(seen[i]);

    if (bet > 0) {
      played++; sum += net; sumSq += net * net; initial += bet;
      if (!counting || sc.calibrate) {
        const k = Math.max(-8, Math.min(8, tc));
        const b = byTC[k] || (byTC[k] = { n: 0, sum: 0, sumSq: 0 });
        b.n++; b.sum += net / bet; b.sumSq += (net / bet) ** 2;
      }
      bankroll += net; if (bankroll > peak) peak = bankroll; if (peak - bankroll > maxDD) maxDD = peak - bankroll;
      if (bankroll < minBank) minBank = bankroll;
    }
    if (mart) {
      mart.rounds++;
      mart.cash += net;
      if (net < 0) mart.cur = Math.min(mart.cur * 2, mart.maxBet);
      else if (net > 0) mart.cur = mart.unit;
      if (mart.cash >= mart.bank + mart.target) { mart.wins++; mart.sessions++; mart.winSum += mart.cash - mart.bank; mart.profit += mart.cash - mart.bank; mart.cash = mart.bank; mart.cur = 1; }
      else if (mart.cash < 1) { mart.busts++; mart.sessions++; mart.profit += mart.cash - mart.bank; mart.cash = mart.bank; mart.cur = 1; }
    }
  }
  return { played, observed, sum, sumSq, initial, byTC, maxDD, mart };
}

// ------------------------------------------------------------------ Scenarios
const EVO = { decks: 8, h17: false, peek: true, das: true, maxHands: 2, surrender: false, bjPays: 1.5, penetration: 0.5 };
const SPREAD_1_8 = [[-99, 1], [2, 2], [3, 4], [4, 6], [5, 8]];
const SPREAD_1_16 = [[-99, 1], [1, 2], [2, 4], [3, 8], [4, 12], [5, 16]];
const SCENARIOS = [
  { id: 'bs_evo', name: 'Temel strateji, düz bahis — 8 deste S17 DAS (tipik canlı masa)', rules: EVO, calibrate: true },
  { id: 'bs_h17', name: 'Temel strateji — 8 deste H17', rules: { ...EVO, h17: true } },
  { id: 'bs_65', name: 'Temel strateji — 8 deste, Blackjack 6:5 öder', rules: { ...EVO, bjPays: 1.2 } },
  { id: 'bs_enhc', name: 'Temel strateji — 8 deste ENHC (krupiye BJ bakmaz, double/split kaybedilir)', rules: { ...EVO, peek: false, enhcLoseAll: true } },
  { id: 'bs_6d_sur', name: 'Temel strateji — 6 deste S17 DAS + teslim (iyi kurallar)', rules: { ...EVO, decks: 6, surrender: true } },
  { id: 'count_1_8', name: 'Hi-Lo sayma + I18, bahis 1–8, her eli oyna, %50 penetrasyon', rules: EVO, count: true, indices: true, spread: SPREAD_1_8 },
  { id: 'count_1_16', name: 'Hi-Lo sayma + I18, bahis 1–16, her eli oyna, %50 penetrasyon', rules: EVO, count: true, indices: true, spread: SPREAD_1_16 },
  { id: 'wong_50', name: 'Hi-Lo Wonging: sadece TC ≥ +1 iken bahis, %50 penetrasyon', rules: EVO, count: true, indices: true, spread: SPREAD_1_8, wongOut: 1 },
  { id: 'wong_75', name: 'Hi-Lo Wonging: sadece TC ≥ +1 iken bahis, %75 penetrasyon', rules: { ...EVO, penetration: 0.75 }, count: true, indices: true, spread: SPREAD_1_8, wongOut: 1 },
  { id: 'count_75', name: 'Hi-Lo sayma, bahis 1–8, her eli oyna, %75 penetrasyon (kara-kumarhane referansı)', rules: { ...EVO, penetration: 0.75 }, count: true, indices: true, spread: SPREAD_1_8 },
  { id: 'martingale', name: 'Martingale (temel strateji + kayıpta ikiye katla), kasa 100 birim, hedef +20, masa limiti 64', rules: EVO, martingale: { bank: 100, target: 20, maxBet: 64 } },
];

function summarize(sc, parts) {
  const agg = { played: 0, observed: 0, sum: 0, sumSq: 0, initial: 0, byTC: {}, maxDD: 0 };
  let mart = null;
  for (const p of parts) {
    agg.played += p.played; agg.observed += p.observed; agg.sum += p.sum; agg.sumSq += p.sumSq; agg.initial += p.initial;
    agg.maxDD = Math.max(agg.maxDD, p.maxDD);
    for (const k in p.byTC) {
      const b = agg.byTC[k] || (agg.byTC[k] = { n: 0, sum: 0, sumSq: 0 });
      b.n += p.byTC[k].n; b.sum += p.byTC[k].sum; b.sumSq += p.byTC[k].sumSq;
    }
    if (p.mart) {
      mart = mart || { sessions: 0, busts: 0, wins: 0, profit: 0, winSum: 0, rounds: 0 };
      mart.sessions += p.mart.sessions; mart.busts += p.mart.busts; mart.wins += p.mart.wins; mart.profit += p.mart.profit; mart.winSum += p.mart.winSum; mart.rounds += p.mart.rounds;
    }
  }
  const n = agg.played;
  const meanPerRound = agg.sum / n;
  const varPerRound = agg.sumSq / n - meanPerRound ** 2;
  const sdPerRound = Math.sqrt(varPerRound);
  const edge = agg.sum / agg.initial; // EV per unit initially wagered
  const se = sdPerRound * Math.sqrt(n) / agg.initial;
  const out = {
    id: sc.id, name: sc.name, rules: BJ.rulesWith(sc.rules),
    roundsObserved: agg.observed, roundsPlayed: n, playFreq: n / agg.observed,
    avgBet: agg.initial / n,
    edgePct: 100 * edge, edgeCI95: 100 * 1.96 * se,
    unitsPer100Observed: 100 * agg.sum / agg.observed,
    sdPerRound,
    // N0: rounds (played) needed for EV to equal one standard deviation
    n0: meanPerRound > 0 ? varPerRound / meanPerRound ** 2 : null,
    // Risk of ruin for a bankroll of B units (diffusion approximation): exp(-2*mu*B/var)
    rorBank: meanPerRound > 0 ? Object.fromEntries([100, 200, 500, 1000].map(B => [B, Math.exp(-2 * meanPerRound * B / varPerRound)])) : null,
  };
  if (Object.keys(agg.byTC).length) {
    out.byTC = Object.fromEntries(Object.keys(agg.byTC).map(Number).sort((a, b) => a - b).map(k => {
      const b = agg.byTC[k]; const m = b.sum / b.n; const v = b.sumSq / b.n - m * m;
      return [k, { n: b.n, freq: b.n / n, evPct: 100 * m, ci95: 100 * 1.96 * Math.sqrt(v / b.n), variance: v }];
    }));
  }
  if (mart) out.martingale = { ...mart, bustRate: mart.busts / mart.sessions, avgProfitPerSession: mart.profit / mart.sessions, avgWin: mart.winSum / mart.wins, avgLoss: (mart.winSum - mart.profit) / mart.busts, roundsPerSession: mart.rounds / mart.sessions };
  return out;
}

// ------------------------------------------------------------------ Main / worker
if (!isMainThread) {
  const { sc, rounds, seed } = workerData;
  parentPort.postMessage(runScenario(sc, rounds, seed));
} else {
  const argv = process.argv.slice(2);
  const ri = argv.indexOf('--rounds');
  const rounds = ri >= 0 ? Number(argv[ri + 1]) : 20e6;
  const only = argv.includes('--only') ? argv[argv.indexOf('--only') + 1].split(',') : null;
  const cores = os.cpus().length;
  (async () => {
    const results = [];
    for (const sc of SCENARIOS) {
      if (only && !only.includes(sc.id)) continue;
      const t0 = Date.now();
      const per = Math.ceil(rounds / cores);
      const parts = await Promise.all(Array.from({ length: cores }, (_, i) => new Promise((res, rej) => {
        const w = new Worker(__filename, { workerData: { sc, rounds: per, seed: 1000 + i * 7919 + sc.id.length * 31 } });
        w.on('message', res); w.on('error', rej);
      })));
      const s = summarize(sc, parts);
      s.seconds = (Date.now() - t0) / 1000;
      results.push(s);
      const fmt = x => (x >= 0 ? '+' : '') + x.toFixed(3);
      console.log(`${sc.id.padEnd(12)} edge ${fmt(s.edgePct)}% ±${s.edgeCI95.toFixed(3)}  avgBet ${s.avgBet.toFixed(2)}  play ${(100 * s.playFreq).toFixed(1)}%  u/100obs ${s.unitsPer100Observed.toFixed(2)}  sd ${s.sdPerRound.toFixed(2)}  ${s.seconds}s`
        + (s.martingale ? `  mart bust ${(100 * s.martingale.bustRate).toFixed(1)}% avgProfit ${s.martingale.avgProfitPerSession.toFixed(2)}` : ''));
    }
    const outDir = __dirname;
    const prev = fs.existsSync(path.join(outDir, 'results.json')) ? JSON.parse(fs.readFileSync(path.join(outDir, 'results.json'))) : { results: [] };
    const merged = prev.results.filter(r => !results.some(x => x.id === r.id)).concat(results);
    merged.sort((a, b) => SCENARIOS.findIndex(s => s.id === a.id) - SCENARIOS.findIndex(s => s.id === b.id));
    const payload = { generated: new Date().toISOString(), roundsPerScenario: rounds, results: merged };
    fs.writeFileSync(path.join(outDir, 'results.json'), JSON.stringify(payload, null, 1));
    fs.writeFileSync(path.join(outDir, 'results.js'), '// generated by sim.js\nwindow.BJ_RESULTS = ' + JSON.stringify(payload) + ';\n');
    // calibration: weighted linear regression of flat-bet EV on true count (TC -4..+6)
    const cal = merged.find(r => r.id === 'bs_evo');
    if (cal && cal.byTC) {
      let sw = 0, sx = 0, sy = 0, sxx = 0, sxy = 0, sv = 0;
      for (const [k, b] of Object.entries(cal.byTC)) {
        const x = Number(k); if (x < -4 || x > 6) continue;
        const w = b.n, y = b.evPct / 100;
        sw += w; sx += w * x; sy += w * y; sxx += w * x * x; sxy += w * x * y; sv += w * b.variance;
      }
      const perTC = (sw * sxy - sx * sy) / (sw * sxx - sx * sx);
      const base = (sy - perTC * sx) / sw;
      const c = { base, perTC, variance: sv / sw, source: 'sim.js bs_evo, ' + rounds + ' rounds' };
      fs.writeFileSync(path.join(outDir, 'calibration.js'), '// generated by sim.js\nwindow.BJ_CAL = ' + JSON.stringify(c, null, 1) + ';\n');
      console.log('calibration', c);
    }
  })();
}
