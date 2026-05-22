'use strict';

const fs = require('fs');
const path = require('path');

const HANOI_PATH = process.env.HANOI_PATH
  || '/Users/freddy/conductor/workspaces/topStepx/hanoi';

if (!fs.existsSync(path.join(HANOI_PATH, 'lib/strategies.js'))) {
  console.error(`source bot not found at ${HANOI_PATH}`);
  process.exit(1);
}

const { STRATEGIES } = require(path.join(HANOI_PATH, 'lib/strategies.js'));
const fn = STRATEGIES.ict.fn;

const inputPath = path.join(__dirname, 'ict_input_bars.json');
const bars = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

const outputs = [];
let currentPos = 0;
for (let i = 0; i < bars.length; i++) {
  const slice = bars.slice(0, i + 1);
  const closes = slice.map((b) => b.c);
  const result = fn(closes, currentPos, slice, {});
  outputs.push({
    i,
    t: bars[i].t,
    c: bars[i].c,
    current_pos_in: currentPos,
    target: result.target,
    meta: result.meta || {},
  });
  currentPos = result.target;
}

const outPath = path.join(__dirname, 'ict_golden.json');
fs.writeFileSync(outPath, JSON.stringify(outputs, null, 2) + '\n');
console.log(`wrote ${outputs.length} reference rows to ${outPath}`);
