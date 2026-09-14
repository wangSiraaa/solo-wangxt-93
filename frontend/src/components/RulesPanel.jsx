import React from "react";

export default function RulesPanel({ rules }) {
  if (!rules) return null;
  const order = [
    ["seat_count", "席位数"],
    ["max_ranks", "最大名次"],
    ["allow_skip_ranks", "允许跳号"],
    ["skipped_rank_handling", "跳号处理"],
    ["duplicate_rank_handling", "重复排名处理"],
    ["overvote_handling", "同一位次多候选"],
    ["invalid_candidate_handling", "无效候选处理"],
    ["exhausted_definition", "穷尽票定义"],
    ["blank_definition", "空白票"],
    ["invalid_definition", "无效票"],
    ["valid_denominator", "过半分母"],
    ["tie_break", "同票决胜（禁止随机）"],
    ["termination", "终止条件"],
    ["conservation", "票数守恒"],
  ];
  return (
    <section className="panel">
      <h2>固定规则快照</h2>
      <div className="muted small">
        版本 <code>{rules.version}</code>。规则在创建选举时固化保存，计票与发布均以此为准。
      </div>
      <div className="rules-grid" style={{ marginTop: 12 }}>
        {order.map(([k, label]) => (
          <div className="rule-item" key={k}>
            <div className="k">{label}</div>
            <div>{String(rules.snapshot[k])}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
