'use strict';

const fs = require('fs');
const path = require('path');

const HANOI_PATH = process.env.HANOI_PATH
  || '/Users/freddy/conductor/workspaces/topStepx/hanoi';

if (!fs.existsSync(path.join(HANOI_PATH, 'lib/strategies/confluence-long.js'))) {
  console.error(`source bot not found at ${HANOI_PATH}`);
  process.exit(1);
}

const confluenceLong = require(
  path.join(HANOI_PATH, 'lib/strategies/confluence-long.js'),
);
const fn = confluenceLong.fn;
const defaultParams = confluenceLong.params || {};
const secondaryUnit = confluenceLong.secondaryUnitNumber || 5;

const inputPath = path.join(__dirname, 'confluence_long_input_bars.json');
const bars = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

function updateAggregatedBars(state, bar, unitNumber) {
  const bucketMs = unitNumber * 60_000;
  const bucketStart = Math.floor(new Date(bar.t).getTime() / bucketMs) * bucketMs;

  if (!state.current || state.bucketStart !== bucketStart) {
    if (state.current) state.closed.push(state.current);
    state.bucketStart = bucketStart;
    state.current = {
      t: new Date(bucketStart).toISOString(),
      o: bar.o,
      h: bar.h,
      l: bar.l,
      c: bar.c,
      v: bar.v || 0,
    };
  } else {
    state.current.h = Math.max(state.current.h, bar.h);
    state.current.l = Math.min(state.current.l, bar.l);
    state.current.c = bar.c;
    state.current.v += bar.v || 0;
  }

  return state.current ? state.closed.concat([state.current]) : state.closed;
}

const secState = { bucketStart: null, current: null, closed: [] };
const outputs = [];
let currentPos = 0;

for (let i = 0; i < bars.length; i++) {
  const bars5m = updateAggregatedBars(secState, bars[i], secondaryUnit);
  const slice = bars.slice(0, i + 1);
  const closes = slice.map((b) => b.c);
  const params = { ...defaultParams, bars5m };
  const result = fn(closes, currentPos, slice, params);
  outputs.push({
    i,
    t: bars[i].t,
    c: bars[i].c,
    current_pos_in: currentPos,
    target: result.target,
    meta: result.meta || {},
    bars5m_len: bars5m.length,
  });
  currentPos = result.target;
}

const outPath = path.join(__dirname, 'confluence_long_golden.json');
fs.writeFileSync(outPath, JSON.stringify(outputs, null, 2) + '\n');
console.log(`wrote ${outputs.length} reference rows to ${outPath}`);
