import React, { useEffect, useState } from "react";
import { api } from "./api";
import RulesPanel from "./components/RulesPanel";
import SummaryPanel from "./components/SummaryPanel";
import RoundPanel from "./components/RoundPanel";
import BallotExplorer from "./components/BallotExplorer";

export default function App() {
  const [rules, setRules] = useState(null);
  const [elections, setElections] = useState([]);
  const [slug, setSlug] = useState("");
  const [election, setElection] = useState(null);
  const [roundNo, setRoundNo] = useState(1);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);

  async function refreshList(keepSlug) {
    const list = await api.elections();
    setElections(list);
    const target = keepSlug || list[0]?.slug;
    if (target && target !== slug) setSlug(target);
    return list;
  }

  async function refreshElection(s) {
    const data = await api.election(s || slug);
    setElection(data);
    setRoundNo((cur) =>
      data.rounds.some((r) => r.round_no === cur) ? cur : 1
    );
  }

  useEffect(() => {
    (async () => {
      setRules(await api.rules());
      const list = await refreshList();
      if (list[0]) setElection(await api.election(list[0].slug));
    })();
  }, []);

  useEffect(() => {
    if (slug) refreshElection(slug).catch(showError);
  }, [slug]);

  function showToast(detail, isError = false) {
    setToast({ detail, isError });
    setTimeout(() => setToast(null), 5200);
  }
  const showError = (e) => showToast(
    e.status === 409 ? `${e.message}（已发布选举拒绝重算/重复发布）` : e.message, true);

  async function recompute() {
    setBusy(true);
    try {
      const d = await api.compute(slug);
      showToast(`重算完成：共 ${d.rounds} 轮，胜者 ${d.winner}`);
      await Promise.all([refreshList(slug), refreshElection()]);
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }

  async function publishResult() {
    setBusy(true);
    try {
      const d = await api.publish(slug);
      showToast(`已发布：${d.publication.rounds_count} 个轮次与输入摘要全部锁定`);
      await Promise.all([refreshList(slug), refreshElection()]);
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }

  const isPublished = election?.status === "published";

  return (
    <div className="app">
      <header className="app-header">
        <h1>单席位排序选择投票（IRV）计票系统</h1>
        <div className="sub">
          社团联合会演示环境 · 全部选票为匿名合成数据，不接入任何真实选举 ·
          规则版本 {rules?.version || "…"}
        </div>
        <div className="badge-row">
          <span className="badge live">✔ 每轮票数守恒校验</span>
          <span className="badge">过半分母＝仍有效票（穷尽票另计）</span>
          <span className="badge warn">同票决胜预先固定、可复现（无随机）</span>
          <span className="badge">发布即锁定，重算不覆盖已公布轮次</span>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <h3>演示选举</h3>
          {elections.map((e) => (
            <button
              key={e.slug}
              className={`election-item ${e.slug === slug ? "active" : ""}`}
              onClick={() => setSlug(e.slug)}
            >
              <div className="name">
                <span className={`dot ${e.status}`} />
                {e.name.length > 20 ? e.name.slice(0, 20) + "…" : e.name}
              </div>
              <div className="meta">
                {e.status === "published" ? "已发布锁定" : "草稿"} ·{" "}
                {e.rounds_count} 轮 · 胜者 {e.winner_code || "—"}
              </div>
            </button>
          ))}
        </aside>

        <main>
          {election && (
            <>
              <div className="row spread" style={{ marginBottom: 12 }}>
                <div className="muted small mono">
                  /api/elections/{election.slug}/
                </div>
                <div className="row">
                  <button onClick={recompute} disabled={busy || isPublished}
                          title={isPublished ? "已发布选举不允许重算" : ""}>
                    重新计票
                  </button>
                  <button className="primary" onClick={publishResult}
                          disabled={busy || isPublished}
                          title={isPublished ? "结果已锁定" : ""}>
                    发布结果并锁定
                  </button>
                </div>
              </div>

              <SummaryPanel election={election} />
              <RoundPanel election={election} roundNo={roundNo}
                          onSelectRound={setRoundNo} />
              <BallotExplorer election={election} />
            </>
          )}
          <RulesPanel rules={rules} />
        </main>
      </div>

      {toast && (
        <div className={`toast ${toast.isError ? "error" : ""}`}>
          {toast.detail}
        </div>
      )}
    </div>
  );
}
