import React from "react";

function Field({ label, children }) {
  return (
    <div style={{ display: "flex", gap: 10, padding: "4px 0" }}>
      <div style={{ width: 150, color: "var(--muted)", flexShrink: 0 }}>{label}</div>
      <div>{children}</div>
    </div>
  );
}

export default function SummaryPanel({ election }) {
  const s = election.input_summary || {};
  const sc = s.status_count || {};
  const pub = election.publication;
  const published = election.status === "published";

  return (
    <section className="panel">
      <div className="row spread">
        <h2>{election.name}</h2>
        {published ? (
          <span className="pill win">已发布 · 结果锁定</span>
        ) : (
          <span className="pill tie">草稿 · 可重算</span>
        )}
      </div>

      <Field label="规则版本">
        <code>{election.rules_version}</code>
      </Field>
      <Field label="候选人">
        {election.candidates.map((c) => (
          <span key={c.code} className="pill" style={{ marginRight: 6 }}>
            {c.code} {c.name}
          </span>
        ))}
      </Field>
      <Field label="投票总数（合成）">{s.ballots_cast ?? "—"} 张</Field>
      <Field label="去脏分类">
        <span className="pill">有效 {sc.valid ?? 0}</span>{" "}
        <span className="pill">首轮即穷尽 {sc.exhausted ?? 0}</span>{" "}
        <span className="pill">空白 {sc.blank ?? 0}</span>{" "}
        <span className="pill" style={{ color: "var(--red)" }}>
          无效 {sc.invalid ?? 0}
        </span>
      </Field>
      <Field label="第一选择分布">
        {Object.entries(s.first_choice || {}).map(([code, n]) => (
          <span key={code} className="pill" style={{ marginRight: 6 }}>
            {code}: {n}
          </span>
        ))}
      </Field>
      <Field label="当选人">
        {election.winner_code ? (
          <strong style={{ color: "var(--green)" }}>
            {election.winner_code}{" "}
            {election.candidates.find((c) => c.code === election.winner_code)?.name || ""}
          </strong>
        ) : (
          <span className="muted">尚未计票</span>
        )}
      </Field>

      <Field label="输入指纹（SHA-256）">
        <span className="mono digest">
          {election.input_digest || "—"}
        </span>
      </Field>

      {published && pub && (
        <div className="lock-banner" style={{ marginTop: 12 }}>
          🔒 发布于 {new Date(pub.published_at).toLocaleString("zh-CN")}：
          输入摘要、规则快照与 {pub.rounds_count} 个轮次均已冻结；
          发布指纹与当前输入指纹{
            election.input_digest === pub.input_digest ? "一致" : "不一致"
          }。对已发布选举发起重算将被拒绝（HTTP 409），不会悄悄覆盖任何已公布轮次。
        </div>
      )}
      {!published && (
        <div className="lock-banner draft" style={{ marginTop: 12 }}>
          草稿态：可反复重算（只重建非冻结轮次）。点击"发布结果"后，输入摘要与全部轮次将被锁定。
        </div>
      )}
    </section>
  );
}
