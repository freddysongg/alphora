import { readNumber, readStringArray } from "../config";
import type { ConfigRecord } from "../config";

const sample: ConfigRecord = {
  debate_depth: 4,
  analysts: ["bull", "bear", 42, null, "macro"],
  llm_model: "gpt-4o-mini",
};

const _depth: number | null = readNumber(sample, "debate_depth");
const _missingNumber: number | null = readNumber(sample, "nope");
const _nullSafeNumber: number | null = readNumber(null, "debate_depth");
const _undefinedSafeNumber: number | null = readNumber(undefined, "debate_depth");

const _analysts: readonly string[] = readStringArray(sample, "analysts");
const _missingArray: readonly string[] = readStringArray(sample, "absent");
const _nullSafeArray: readonly string[] = readStringArray(null, "analysts");
const _undefinedSafeArray: readonly string[] = readStringArray(
  undefined,
  "analysts",
);

const _depthIsFour: boolean = _depth === 4;
const _missingNumberIsNull: boolean = _missingNumber === null;
const _stringArrayFiltered: boolean =
  _analysts.length === 3 && _analysts[0] === "bull";
const _missingArrayIsEmpty: boolean = _missingArray.length === 0;

void _depth;
void _missingNumber;
void _nullSafeNumber;
void _undefinedSafeNumber;
void _analysts;
void _missingArray;
void _nullSafeArray;
void _undefinedSafeArray;
void _depthIsFour;
void _missingNumberIsNull;
void _stringArrayFiltered;
void _missingArrayIsEmpty;

export {};
