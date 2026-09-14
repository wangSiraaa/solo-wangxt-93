import React, { useMemo } from "react";
import { destName } from "../format";

function ConservationBar({ round }) {
  const cells = [
    ["valid", "仍有效票", round.valid],
    ["exhausted", "穷尽票", round.exhausted],
    ["blank", "空白票", round.blank],
    ["invalid", "无效票", round.invalid],
  ];
  const total = round.valid + round.exhausted + round.blank + round.invalid;
  const ok = total === round.ballots_cast;
  return (
    <>
      <div className="conservation">
        {cells.map(([cls, lbl, n]) => (
          <div className={`cell ${cls}`} key={cls}>
            <div className="num">{n}</div>
            <div className="lbl">{lbl}</div>
          </div>
        ))}
      </div>
      <div className={ok ? "check-ok" : "check-bad"}>
        {ok ? "✔" : "✘"} 票数守恒：仍有效 {round.valid} + 穷尽 {round.exhausted} +
        空白 {round.blank} + 无效 {round.invalid} = {total}，
        投票总数 {round.ballots_cast}（{ok ? "守恒成立" : "守恒失败！"}）
      </div>
    </>
  );
}

function CountsTable({ round, candidateMap }) {
  const max = Math.max(1, ...Object.values(round.counts));
  const eliminated = new Set(round.eliminated);
  return (
    <table>
      <thead>
        <tr>
          <th style={{ width: 150 }}>候选人</th>
          <th>本轮得票</th>
          <th style={{ width: 90 }}>票数</th>
          <th style={{ width: 120 }}>状态</th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(round.counts)
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
          .map(([code, votes]) => {
            const isWinner = round.winner === code;
            const isOut = eliminated.has(code);
            const pct = (votes / max) * 100;
            return (
              <tr key={code}>
                <td>
                  <strong>{code}</strong>{" "}
                  <span className="muted">{candidateMap[code] || ""}</span>
                </td>
                <td>
                  <div className="bar-track">
                    <div
                      className={`bar-fill ${isWinner ? "winner" : isOut ? "eliminated" : ""}`}
                      style={{ width: `${pct}%` }}
                    />
                    <span className="bar-votes">{votes}</span>
                  </div>
                </td>
                <td>{votes}</td>
                <td>
                  {isWinner && <span className="pill win">本轮胜出</span>}
                  {isOut && <span className="pill out">本轮淘汰</span>}
                  {!isWinner && !isOut && <span className="pill">继续</span>}
                </td>
              </tr>
            );
          })}
      </tbody>
    </table>
  );
}

function FlowMatrix({ round, candidateMap }) {
  if (!round.flows || round.flows.length === 0) {
    return (
      <div className="muted small" style={{ marginTop: 10 }}>
        第一轮：选票按各自第一选择落位，尚无轮次间转移。
      </div>
    );
  }
  return (
    <div style={{ marginTop: 12 }}>
      <h3 style={{ marginTop: 0 }}>选票去向（相对上一轮发生转移的票，共{" "}
        {round.flows.reduce((s, f) => s + f.count, 0)} 张）</h3>
      <div className="flow-grid">
        {round.flows.map((f, i) => {
          const toExh = f.to === "EXHAUSTED";
          return (
            <React.Fragment key={i}>
              <div className="flow-card">
                <strong>{destName(f.from, candidateMap)}</strong>
                <span className="muted">（原落点出局）</span>
              </div>
              <div className="flow-arrow">→</div>
              <div className={`flow-card ${toExh ? "exh" : ""}`}>
                <strong>{destName(f.to, candidateMap)}</strong>
                <span className="count-pill"> ×{f.count} 张</span>
                <div className="flow-codes">{f.ballots.join("、")}</div>
              </div>
              <div />
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

export default function RoundPanel({ election, roundNo, onSelectRound }) {
  const candidateMap = useMemo(
    () => Object.fromEntries(election.candidates.map((c) => [c.code, c.name])),
    [election.candidates]
  );

  const current =
    election.rounds.find((r) => r.round_no === roundNo) ||
    election.rounds[0];

  const isWinnerRound = !!current.winner;
  return (
    <section className="panel">
      <div className="row spread">
        <h2>第 {current.round_no} 轮计票</h2>
        <div>
          {current.frozen && <span className="pill win">已冻结（随发布锁定）</span>}
        </div>
      </div>

      <div className="round-tabs" style={{ marginTop: 10 }}>
        {election.rounds.map((r) => (
          <button
            key={r.round_no}
            className={`round-tab ${r.round_no === current.round_no ? "active" : ""} ${r.winner ? "final" : ""}`}
            onClick={() => onSelectRound(r.round_no)}
          >
            第 {r.round_no} 轮{r.winner ? " ★" : ""}
          </button>
        ))}
      </div>

      <div className="row" style={{ gap: 18 }}>
        <div>
          过半门槛（分母＝仍有效票 {current.valid}）：
          <strong style={{ color: "var(--accent)" }}>
            {" "}{current.majority_threshold ?? "—"}
          </strong>
        </div>
        <div className="muted small">
          floor({current.valid}/2)+1；穷尽/空白/无效票不进分母
        </div>
      </div>

      <ConservationBar round={current} />
      <CountsTable round={current} candidateMap={candidateMap} />

      <div className={`note-box ${isWinnerRound ? "win" : ""}`}
           style={{ marginTop: 12 }}>
        {current.tie_break_used && (
          <span className="pill tie">触发固定决胜（非随机）</span>
        )}{" "}
        {current.elimination_note}
      </div>

      <FlowMatrix round={current} candidateMap={candidateMap} />
    </section>
  );
}
