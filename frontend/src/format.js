export const DEST_LABELS = {
  EXHAUSTED: "穷尽",
  BLANK: "空白",
  INVALID: "无效",
};

export function destName(d, candidates) {
  if (DEST_LABELS[d]) return DEST_LABELS[d];
  return candidates[d] ? `${d} ${candidates[d]}` : d;
}

export function statusLabel(s) {
  return { valid: "有效", exhausted: "穷尽", blank: "空白", invalid: "无效" }[s] || s;
}

export function statusClass(s) {
  return { valid: "win", exhausted: "exh", blank: "", invalid: "bad" }[s] || "";
}
