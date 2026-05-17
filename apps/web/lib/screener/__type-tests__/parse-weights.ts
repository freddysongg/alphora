import {
  FACTOR_KEYS,
  WEIGHT_FIELD_PREFIX,
  formDataToWeights,
  makeDefaultWeights,
  recordToWeights,
} from "../parse-weights";
import type { FactorKey, FactorWeights } from "../parse-weights";

const _defaults: FactorWeights = makeDefaultWeights();
const _qualityKey: FactorKey = "quality";
const _allKeys: readonly FactorKey[] = FACTOR_KEYS;

const formData = new FormData();
formData.set(`${WEIGHT_FIELD_PREFIX}quality`, "0.5");
formData.set(`${WEIGHT_FIELD_PREFIX}valuation`, "2");
formData.set(`${WEIGHT_FIELD_PREFIX}momentum`, "not-a-number");

const _parsed: FactorWeights = formDataToWeights(formData);
const _qualityIsHalf: boolean = _parsed.quality === 0.5;
const _valuationClamped: boolean = _parsed.valuation === 1;
const _momentumFallsBack: boolean = _parsed.momentum === 0;

const _coerced: FactorWeights = recordToWeights({
  quality: 0.3,
  unknown: 0.9,
  valuation: -1,
});
const _unknownIgnored: boolean = _coerced.valuation === 0;

void _defaults;
void _qualityKey;
void _allKeys;
void _parsed;
void _qualityIsHalf;
void _valuationClamped;
void _momentumFallsBack;
void _coerced;
void _unknownIgnored;

export {};
