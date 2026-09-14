import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { destName, statusLabel } from "../format";

export default function BallotExplorer({ election }) {
  const [filter, setFilter] = useState("all");
  const [code, setCode] = useState("");
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  const candidateMap = useMemo(
    () => Object.fromEntries(election.candidates.map((c) => [c.code, c.name])),
    [election.candidates]
  );
  const chains = election.chains || {};

  const filtered = useMemo(() => {
    const list = election.ballots || [];
    if (filter === "all") return list;
    return list.filter((b) => b.status === filter);
  }, [election.ballots, filter]);

  useEffect(() => {
    // 切换选举时重置到该选举的第一张选票
    const first = (election.ballots || [])[0];
    if (first) load(first.code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [election.slug]);

  async function load(c) {
    setCode(c);
    setError("");
    try {
      setDetail(await api.ballotChain(election.slug, c));
    } catch (e) {
      setError(e.message);
      setDetail(null);
    }
  }

  return (
    <section className="panel">
      <h2>匿名选票转移链追踪</h2>
      <div className="muted small">
        所有选票均为合成代号（B001…），不含真实选民信息。输入代号可精确查询，
        也可按去脏状态筛选。每轮落点、转移原因、被剔除条目均可核对。
      </div>

      <div className="ballot-controls" style={{ marginTop: 12 }}>
        <select value={filter} onChange={(e) => {
          setFilter(e.target.value);
          const first = (election.ballots || [])
            .find((b) => e.target.value === "all" || b.status === e.target.value);
          if (first) load(first.code);
        }}>
          <option value="all">全部状态</option>
          <option value="valid">有效票</option>
          <option value="exhausted">穷尽票</option>
          <option value="blank">空白票</option>
          <option value="invalid">无效票</option>
        </select>
        <input
          list="ballot-codes"
          placeholder="输入选票代号，如 B121"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(code.trim())}
          style={{ width: 220 }}
        />
        <datalist id="ballot-codes">
          {filtered.slice(0, 300).map((b) => (
            <option key={b.code} value={b.code}>{statusLabel(b.status)}</option>
          ))}
        </datalist>
        <button onClick={() => load(code.trim())}>查询转移链</button>
        <span className="muted small">符合筛选：{filtered.length} 张</span>
      </div>

      {error && <div className="error-box">{error}</div>}

      {detail && (
        <div>
          <div className="row spread" style={{ alignItems: "flex-start" }}>
            <table style={{ maxWidth: 560 }}>
              <tbody>
                <tr><th>选票代号</th><td className="mono">{detail.code}</td></tr>
                <tr><th>原始排名</th><td className="mono">
                  {JSON.stringify(detail.raw_ranking) || "{}"}
                </td></tr>
                <tr><th>规范化后</th><td className="mono">
                  {detail.normalized_ranking?.join(" › ") || "（空）"}
                </td></tr>
                <tr><th>去脏状态</th><td>
                  <span className={`pill ${detail.status === "invalid" ? "out" : ""}`}>
                    {statusLabel(detail.status)}
                  </span> {detail.reason}
                </td></tr>
              </tbody>
            </table>
            <div style={{ maxWidth: 380 }}>
              {detail.dropped?.length > 0 && (
                <>
                  <h3 style={{ marginTop: 0 }}>被忽略的条目</h3>
                  {detail.dropped.map((d, i) => (
                    <div className="dropped-item" key={i}>
                      名次 {d.rank} → {String(d.candidate)}：{d.reason}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>

          <h3>逐轮落点（转移链）</h3>
          <div className="chain">
            {(chains[detail.code] || detail.chain || []).map((step, i, arr) => {
              const cls =
                step.destination === "EXHAUSTED" ? "exh"
                : step.destination === "INVALID" || step.destination === "BLANK" ? "bad"
                : step.destination === election.winner_code && i === arr.length - 1 ? "win"
                : "";
              return (
                <React.Fragment key={i}>
                  {i > 0 && <span className="chain-arrow">→</span>}
                  <div className={`chain-step ${cls}`} title={step.reason}>
                    <div className="r">第 {step.round} 轮</div>
                    <div className="d">{destName(step.destination, candidateMap)}</div>
                  </div>
                </React.Fragment>
              );
            })}
          </div>
          <div className="muted small" style={{ marginTop: 8 }}>
            最后一步原因：{(chains[detail.code] || detail.chain || []).slice(-1)[0]?.reason}
          </div>
        </div>
      )}
    </section>
  );
}
