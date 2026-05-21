// Generate the bar-for-bar reference output of the source bot's
// `filtered` strategy on the committed input series. Run from
// `services/api/`:
//
//   node tests/fixtures/generate_macd_rsi_adx_golden.cjs
//
// Rewrites `tests/fixtures/macd_rsi_adx_golden.json`. The committed
// JSON is what the Python golden test asserts against; regenerate only
// when you regenerate the input bars or intentionally cut over to a new
// upstream snapshot of the source bot.
//
// Requires the source bot at the absolute path below. If you've moved
// it, edit HANOI_PATH or set the HANOI_PATH env var before running.
'use strict';

const fs = require('fs');
const path = require('path');

const HANOI_PATH = process.env.HANOI_PATH
  || '/Users/freddy/conductor/workspaces/topStepx/hanoi';

if (!fs.existsSync(path.join(HANOI_PATH, 'lib/strategies.js'))) {
  console.error(
    `source bot not found at ${HANOI_PATH}; set HANOI_PATH env var or `
    + 'install the source bot at the default location before re-running.',
  );
  process.exit(1);
}

const { STRATEGIES } = require(path.join(HANOI_PATH, 'lib/strategies.js'));
const filteredFn = STRATEGIES.filtered.fn;

const inputPath = path.join(__dirname, 'macd_rsi_adx_input_bars.json');
const bars = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

const outputs = [];
let currentPos = 0;
for (let i = 0; i < bars.length; i++) {
  const slice = bars.slice(0, i + 1);
  const closes = slice.map((b) => b.c);
  const result = filteredFn(closes, currentPos, slice, {});
  outputs.push({
    i,
    t: bars[i].t,
    c: bars[i].c,
    current_pos_in: currentPos,
    target: result.target,
    meta: result.meta || {},
  });
  // Drive position to whatever target says; matches the no-friction
  // simulator used by the Python golden test (Task 14).
  currentPos = result.target;
}

const outPath = path.join(__dirname, 'macd_rsi_adx_golden.json');
fs.writeFileSync(outPath, JSON.stringify(outputs, null, 2) + '\n');
console.log(`wrote ${outputs.length} reference rows to ${outPath}`);
