/*
 * Blackjack engine: shoe-composition-dependent EV calculation + basic strategy generation
 * + Hi-Lo counting. The same file is used by the Node simulator (sim.js) and the browser advisor (index.html).
 *
 * Card codes: 1 = Ace, 2..9, 10 = any ten-value card (10/J/Q/K).
 * Shoe: array of length 11, shoe[r] = number of rank r cards left, shoe[0] = total cards left.
 */
(function (root) {
  'use strict';

  const DEFAULT_RULES = {
    decks: 8,
    h17: false,          // true: dealer hits soft 17
    peek: true,          // true: dealer checks for BJ (US hole card); false: ENHC (European no-hole-card)
    enhcLoseAll: true,   // ENHC only: on dealer BJ, double/split stakes are lost as well
    das: true,           // double after split
    doubleAny: true,     // false: double only on 9-11
    maxHands: 2,         // 2 = split only once
    surrender: false,    // late surrender
    bjPays: 1.5,         // 1.5 = 3:2, 1.2 = 6:5
    penetration: 0.5,    // fraction of the shoe dealt before the shuffle
  };

  function rulesWith(over) { return Object.assign({}, DEFAULT_RULES, over || {}); }

  function newShoe(decks) {
    const s = new Array(11).fill(0);
    for (let r = 1; r <= 9; r++) s[r] = 4 * decks;
    s[10] = 16 * decks;
    s[0] = 52 * decks;
    return s;
  }

  function removeCard(s, r) { if (s[r] > 0) { s[r]--; s[0]--; } return s; }

  // Hi-Lo tag
  function hiLo(r) { return (r >= 2 && r <= 6) ? 1 : (r === 1 || r === 10) ? -1 : 0; }

  function effTotal(hard, ace) { return (ace && hard + 10 <= 21) ? hard + 10 : hard; }

  // ---------------------------------------------------------------- Dealer
  // Returns {p:[P17,P18,P19,P20,P21,Pbust] conditioned on dealer having no BJ, bj: P(dealer BJ)}
  function dealerDist(up, shoe, rules) {
    const out = [0, 0, 0, 0, 0, 0];
    const s = shoe.slice();
    let bj = 0;
    const tot = s[0];
    for (let r = 1; r <= 10; r++) {
      if (!s[r]) continue;
      const pr = s[r] / tot;
      if ((up === 1 && r === 10) || (up === 10 && r === 1)) { bj += pr; continue; }
      s[r]--; s[0]--;
      dealerRec(up + r, up === 1 || r === 1, s, pr, out, rules.h17);
      s[r]++; s[0]++;
    }
    const k = 1 - bj;
    if (k > 0) for (let i = 0; i < 6; i++) out[i] /= k;
    return { p: out, bj };
  }

  function dealerRec(hard, ace, s, prob, out, h17) {
    const t = effTotal(hard, ace);
    if (t > 21) { out[5] += prob; return; }
    if (t >= 17) {
      const soft17 = (t === 17 && ace && hard + 10 === 17);
      if (!(soft17 && h17)) { out[t - 17] += prob; return; }
    }
    const tot = s[0];
    if (tot <= 0) { out[Math.min(t, 21) >= 17 ? t - 17 : 0] += prob; return; }
    for (let r = 1; r <= 10; r++) {
      if (!s[r]) continue;
      const pr = prob * s[r] / tot;
      if (pr < 1e-12) continue;
      s[r]--; s[0]--;
      dealerRec(hard + r, ace || r === 1, s, pr, out, h17);
      s[r]++; s[0]++;
    }
  }

  // ---------------------------------------------------------------- Player
  function standEV(t, P) {
    if (t > 21) return -1;
    if (t < 17) return P[5] - (1 - P[5]);
    let win = P[5], lose = 0;
    for (let d = 17; d <= 21; d++) {
      if (d < t) win += P[d - 17]; else if (d > t) lose += P[d - 17];
    }
    return win - lose;
  }

  function makeSolver(P) {
    const memo = new Map();
    function key(hard, ace, s) { return hard + (ace ? 'a' : 'h') + s.join(','); }
    // best EV standing or hitting (no double), for an existing hand
    function best(hard, ace, s) {
      const t = effTotal(hard, ace);
      if (t > 21) return -1;
      const st = standEV(t, P);
      if (t === 21) return st;
      return Math.max(st, hit(hard, ace, s));
    }
    function hit(hard, ace, s) {
      const k = key(hard, ace, s);
      const m = memo.get(k);
      if (m !== undefined) return m;
      let ev = 0;
      const tot = s[0];
      for (let r = 1; r <= 10; r++) {
        if (!s[r]) continue;
        const pr = s[r] / tot;
        s[r]--; s[0]--;
        ev += pr * best(hard + r, ace || r === 1, s);
        s[r]++; s[0]++;
      }
      memo.set(k, ev);
      return ev;
    }
    function dbl(hard, ace, s) { // EV per original unit, i.e. already x2
      let ev = 0;
      const tot = s[0];
      for (let r = 1; r <= 10; r++) {
        if (!s[r]) continue;
        ev += (s[r] / tot) * standEV(effTotal(hard + r, ace || r === 1), P);
      }
      return 2 * ev;
    }
    return { best, hit, dbl, stand: (hard, ace) => standEV(effTotal(hard, ace), P) };
  }

  function canDoubleTotal(rules, hard, ace) {
    if (rules.doubleAny) return true;
    const t = effTotal(hard, ace);
    return !ace && t >= 9 && t <= 11;
  }

  /*
   * Full analysis of a decision.
   * cards: player's cards in this hand, up: dealer upcard,
   * shoe: remaining shoe with EVERY card already seen removed (player's cards, upcard, other players' cards ...)
   * opts: {afterSplit, nHands} for availability of options
   * Returns EV per original unit stake for each available action.
   */
  function analyze(cards, up, shoe, rules, opts) {
    rules = rulesWith(rules);
    opts = opts || {};
    const hard = cards.reduce((a, b) => a + b, 0);
    const ace = cards.includes(1);
    const n = cards.length;
    const t = effTotal(hard, ace);
    const res = { total: t, soft: ace && hard + 10 <= 21, ev: {}, best: null };
    const ins = shoe[0] ? shoe[10] / shoe[0] : 0;
    if (up === 1) res.insuranceEV = 3 * ins - 1; // per unit of insurance stake

    const dd = dealerDist(up, shoe, rules);
    const pbj = rules.peek ? 0 : dd.bj; // with peek, a decision only happens when the dealer has no BJ
    res.dealer = dd;
    if (n === 2 && t === 21 && !opts.afterSplit) {
      res.blackjack = true;
      res.ev.stand = (1 - dd.bj) * rules.bjPays; // EV of the natural, unconditioned
      res.best = 'stand';
      return res;
    }
    const solver = makeSolver(dd.p);
    const wrap = (evNoBj, cost) => (1 - pbj) * evNoBj - pbj * cost;
    const lostDouble = rules.enhcLoseAll ? 2 : 1;

    res.ev.stand = wrap(solver.stand(hard, ace), 1);
    if (t < 21) res.ev.hit = wrap(solver.hit(hard, ace, shoe), 1);
    const twoCards = n === 2;
    if (twoCards && t < 21 && canDoubleTotal(rules, hard, ace) && (!opts.afterSplit || rules.das)) {
      res.ev.double = wrap(solver.dbl(hard, ace, shoe), lostDouble);
    }
    if (twoCards && cards[0] === cards[1] && (opts.nHands || 1) < rules.maxHands) {
      res.ev.split = wrap(splitEV(cards[0], shoe, rules, dd.p), lostDouble);
    }
    if (twoCards && rules.surrender && !opts.afterSplit) res.ev.surrender = -0.5;
    let bestA = null, bestV = -Infinity;
    for (const a in res.ev) if (res.ev[a] > bestV) { bestV = res.ev[a]; bestA = a; }
    res.best = bestA;
    return res;
  }

  // Approximation: each split hand is played independently, no resplit, split aces receive one card.
  function splitEV(r, shoe, rules, P) {
    const s = shoe.slice();
    const solver = makeSolver(P);
    let ev = 0;
    const tot = s[0];
    for (let c = 1; c <= 10; c++) {
      if (!s[c]) continue;
      const pr = s[c] / tot;
      s[c]--; s[0]--;
      const hard = r + c, ace = r === 1 || c === 1;
      let v;
      if (r === 1) v = standEV(effTotal(hard, ace), P);
      else {
        v = solver.best(hard, ace, s);
        if (rules.das && canDoubleTotal(rules, hard, ace)) v = Math.max(v, solver.dbl(hard, ace, s));
      }
      ev += pr * v;
      s[c]++; s[0]++;
    }
    return 2 * ev;
  }

  // ---------------------------------------------------------------- Basic strategy
  // Codes: S stand, H hit, D double-else-hit, Ds double-else-stand, R surrender-else-hit, Rs surrender-else-stand
  const UPS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1];
  const HARD_REP = { 5: [2, 3], 6: [2, 4], 7: [2, 5], 8: [3, 5], 9: [4, 5], 10: [4, 6], 11: [5, 6] };
  function repHard(t) { if (t <= 11) return HARD_REP[t]; return [10, t - 10]; }

  function code(ev) {
    const sh = (ev.hit !== undefined && ev.hit > ev.stand) ? 'H' : 'S';
    let best = sh === 'H' ? 'hit' : 'stand', bv = ev[best];
    if (ev.double !== undefined && ev.double > bv) { best = 'double'; bv = ev.double; }
    if (ev.surrender !== undefined && ev.surrender > bv) { best = 'surrender'; bv = ev.surrender; }
    if (best === 'double') return sh === 'H' ? 'D' : 'Ds';
    if (best === 'surrender') return sh === 'H' ? 'R' : 'Rs';
    return sh;
  }

  function generateStrategy(rules) {
    rules = rulesWith(rules);
    const full = newShoe(rules.decks);
    const hard = {}, soft = {}, pair = {};
    for (const up of UPS) {
      hard[up] = {}; soft[up] = {}; pair[up] = {};
      for (let t = 5; t <= 20; t++) {
        const cards = repHard(t);
        const s = full.slice(); cards.forEach(c => removeCard(s, c)); removeCard(s, up);
        hard[up][t] = code(analyze(cards, up, s, rules).ev);
      }
      hard[up][4] = 'H'; hard[up][21] = 'S';
      for (let t = 13; t <= 20; t++) {
        const cards = [1, t - 11];
        const s = full.slice(); cards.forEach(c => removeCard(s, c)); removeCard(s, up);
        soft[up][t] = code(analyze(cards, up, s, rules).ev);
      }
      soft[up][12] = 'H'; soft[up][21] = 'S';
      for (let r = 1; r <= 10; r++) {
        const s = full.slice(); removeCard(s, r); removeCard(s, r); removeCard(s, up);
        const a = analyze([r, r], up, s, rules);
        let others = -Infinity;
        for (const k in a.ev) if (k !== 'split') others = Math.max(others, a.ev[k]);
        pair[up][r] = a.ev.split !== undefined && a.ev.split > others;
      }
    }
    return { hard, soft, pair };
  }

  // ---------------------------------------------------------------- Hi-Lo index plays (Illustrious 18 + Fab 4)
  // [type, total, up, index, action-at-or-above-index]
  const INDEX_PLAYS = [
    ['hard', 16, 10, 0, 'S'], ['hard', 15, 10, 4, 'S'], ['pair', 10, 5, 5, 'P'], ['pair', 10, 6, 4, 'P'],
    ['hard', 10, 10, 4, 'D'], ['hard', 12, 3, 2, 'S'], ['hard', 12, 2, 3, 'S'], ['hard', 11, 1, 1, 'D'],
    ['hard', 9, 2, 1, 'D'], ['hard', 10, 1, 4, 'D'], ['hard', 9, 7, 3, 'D'], ['hard', 16, 9, 5, 'S'],
    ['hard', 13, 2, -1, 'S'], ['hard', 12, 4, 0, 'S'], ['hard', 12, 5, -2, 'S'], ['hard', 12, 6, -1, 'S'],
    ['hard', 13, 3, -2, 'S'],
  ];
  const SURR_INDEX = [[14, 10, 3], [15, 10, 0], [15, 9, 2], [15, 1, 1]];

  // Linear player-advantage model from the simulator (overwritten by calibration.js if present)
  const CAL = { base: -0.0045, perTC: 0.0050, variance: 1.32 };

  function advantage(tc, cal) { cal = cal || root.BJ_CAL || CAL; return cal.base + cal.perTC * tc; }

  const api = {
    DEFAULT_RULES, rulesWith, newShoe, removeCard, hiLo, effTotal,
    dealerDist, standEV, analyze, splitEV, generateStrategy, UPS,
    INDEX_PLAYS, SURR_INDEX, CAL, advantage,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BJ = api;
})(typeof window !== 'undefined' ? window : globalThis);
