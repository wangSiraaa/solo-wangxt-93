# IRV 单席位排序选择投票计票系统（合成数据演示）

为社团联合会准备的 **Instant-Runoff Voting（排序复选/单席位可转移投票）** 计票演示系统。
**不接入任何真实选举**，库内全部为匿名合成选票（代号 `B001…`）。

- **React**：逐轮展示票数、守恒校验、选票去向、匿名票转移链、规则快照、发布锁定状态
- **Django REST Framework**：固定 IRV 规则引擎（无随机数）、计票/重算/发布 API
- **PostgreSQL**：保存匿名合成选票、候选人、规则快照、逐轮结果（JSONField）与发布记录

## 规则（版本 `2026.irv-sfu.v1`，创建选举时固化为快照）

| 议题 | 本次明确规定 |
| --- | --- |
| 重复排名 | 同一候选人代号在一张票中重复出现 → **整张票 invalid（作废）** |
| 同一位次多候选（overvote） | 同一位次写多个代号 → **整张票 invalid**，不静默选取 |
| 无效候选 | 名次指向名单外代号时**仅忽略该条目**，其余合法排名照常生效；若去脏后无任何合法条目且原票非空 → 自第一轮起计为 exhausted |
| 跳号 | 允许（如名次 1、3、5），按名次升序读取，空缺按不存在处理，不判废 |
| 穷尽票 | 选票合法但榜上候选已全部出局（或去脏后无合法候选）→ `exhausted`，与仍有效票**分开统计** |
| 过半分母 | **仍有效票数 valid**（不含 exhausted/blank/invalid）；门槛 `floor(valid/2)+1` |
| 同票决胜 | **预先固定、可复现、禁止随机**：第一轮僵局按代号字典序（小者先淘汰）；其后按「第一轮得票少者先淘汰 → 代号字典序小者先淘汰」；最低票并列时每轮只淘汰决胜第一名，其余进入下一轮；最终两人平票均未过半时，第一轮得票高者胜，相同则代号靠后者胜 |
| 终止 | 严格过半即胜；仅剩一人时直接当选；最终两人平票按上述固定决胜 |
| 票数守恒 | 每轮断言 `valid + exhausted + blank + invalid == ballots_cast`，失败即报错 |

## 演示剧本

### `sf-union-2026`（172 张，默认草稿态，可在界面发布）
1. **首轮无过半**：A42 / B40 / C20 / D12 / E12 / F12，门槛 70，最高仅 42；
   D/E/F 三方 12 平票 → 按代号字典序固定决胜淘汰 **D**。
2. **连续转移**：R2 D 的 12 票 → C；E/F 仍平（首轮得票相同）再按代号淘汰 **E**；
   R3 E 的 12 票 → A，淘汰 **F**（F 的票 → C）；R4 淘汰 **B**。
3. **大量穷尽票**：28 张票首轮即穷尽（只填了无效代号）；16 张只选 B 的票在 B 出局后
   **中途穷尽**。终轮 valid=122、exhausted=44，C=68 ≥ 门槛 62 胜出。
4. 选票浏览器输入 `B121` 可看 `B→B→B→B→穷尽` 的完整链；`B169` 可看
   「无效候选条目被忽略但票仍有效」的去脏记录；`B158` 等为 invalid。

### `tie-final-demo`（100 张，默认已发布锁定）
P42 / Q42 / R16 → R 出局但其票全部穷尽 → 最终 P42:Q42 平票，均不过半；
首轮得票相同（42=42）→ 代号字典序靠后者 **Q** 当选。

### 发布锁定
- 草稿态可反复「重新计票」（删除并重建非冻结轮次）；
- 「发布结果」会保存 Publication（输入摘要 + SHA-256 指纹 + 规则快照），全部轮次置 `frozen`；
- 发布后任何重算/重复发布返回 **HTTP 409**，已公布轮次绝不被覆盖；
- 输入指纹对「规范化 JSON（代号/名次排序、去空白）」取 SHA-256，锁定页展示发布指纹与当前指纹是否一致。

## 快速开始

### 方式一：一键脚本（本机已有 PostgreSQL 或用 micromamba 便携版）

```bash
# 若还没有 PostgreSQL（无 root 环境）：
# micromamba create -y -p ~/pgenv -c conda-forge postgresql=16
bash scripts/start_demo.sh
# UI:  http://127.0.0.1:5173
# API: http://127.0.0.1:8000/api/
```

### 方式二：手动

```bash
# 1. 数据库
createdb -h /tmp -U postgres irv          # 或任意 PG 实例，用 PG* 环境变量指定

# 2. 后端
cd backend/irv_system
pip install -r ../requirements.txt
# 每次本地启动都设置自己的运行时密钥；不要写入仓库或 .env.example。
export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
python manage.py migrate
python manage.py seed_demo --main-draft   # --no-publish 全部草稿；无参数全部发布
python manage.py runserver 127.0.0.1:8000

# 3. 前端
cd ../../frontend
npm install
npm run dev
```

数据库连接默认：`PGHOST=/tmp PGPORT=5432 PGUSER=postgres PGDATABASE=irv`；
也支持由运行环境设置的 `DATABASE_URL`；
`USE_SQLITE=1` 仅用于本地单元测试（正式演示请用 PostgreSQL）。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/rules/` | 固定规则快照 |
| GET/POST | `/api/elections/` | 列表 / 创建（slug、候选人、选票） |
| GET | `/api/elections/<slug>/` | 完整数据：规则、摘要、全部轮次、选票、转移链 |
| POST | `/api/elections/<slug>/compute/` | 草稿态计票/重算；已发布 → 409 |
| POST | `/api/elections/<slug>/publish/` | 发布并锁定；重复发布 → 409 |
| GET | `/api/elections/<slug>/ballots/<code>/` | 单张匿名票的去脏记录与逐轮转移链 |

选票 JSON 示例：

```json
{"code": "B001", "ranking": {"1": "A", "2": "F", "3": "C"}}
{"code": "B002", "ranking": {"1": "Z", "3": "A"}}
{"code": "B003", "ranking": {"1": ["D", "A"]}}
```

## 测试

```bash
cd backend/irv_system
USE_SQLITE=1 python manage.py test irv        # 30 个测试：去脏/守恒/决胜/穷尽/锁定/API
```

引擎为纯 Python 模块 `irv/engine.py`（不依赖 ORM），决胜只用代号排序与首轮得票，
同输入多次计票结果逐轮一致（有确定性回归测试）。

## 目录

```
backend/irv_system/
  irv/engine.py        # IRV 纯逻辑引擎 + 规则快照（核心）
  irv/digest.py        # 输入规范化与 SHA-256 指纹
  irv/models.py        # Election/Candidate/Ballot/Round/Publication
  irv/services.py      # 计票落库、发布锁定（事务）
  irv/views.py         # DRF API
  irv/management/commands/seed_demo.py
frontend/src/
  App.jsx
  components/ RulesPanel / SummaryPanel / RoundPanel / BallotExplorer
scripts/start_demo.sh
```
