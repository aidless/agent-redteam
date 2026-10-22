# 红队覆盖矩阵 Demo

[**Live demo**](https://aidless.github.io/agent-redteam/) · 本地回放与实时重跑见下。

**一句话**：12 类攻击 × 5 层防御，逐格显示真实 defense 类对真实攻击样本做了什么：
`BLOCK` / `MODIFY` / `FLAG` / `ALLOW` / 未行使。

这是**层内覆盖矩阵**，不是端到端多代理运行。脚本化响应模拟一个会中招的目标，
用来行使 defense 类；它不是真实 LLM 输出。

## 30 秒开始

```bash
cd agent-redteam
python3 demo/server.py                  # http://127.0.0.1:8000/
```

本地模式会先跑全部层内检查，然后提供：

- `GET /api/health`
- `GET /api/matrix` / `GET /matrix.json`
- `POST /api/run`：重新执行矩阵
- `GET /config.json`：`{"mode": "live"}`

静态回放：

```bash
python3 demo/build_static.py            # 写 demo/public/matrix.json
python3 -m http.server -d demo/public   # 任意静态服务器
```

构建脚本会核对 10 条预定动作；任何一条偏差都会以非零退出码结束。

## 测试

```bash
python3 -m unittest demo/test_demo.py -v
```

覆盖：矩阵形状与 summary 折叠、关键层的实际动作、expected miss、FLAG 不算 BLOCK、
已提交 `matrix.json` 与当前代码一致、UI 不硬编码指标、无密钥/绝对路径、本地 HTTP API。

## 三分钟面试讲法

1. 先讲矩阵：行是 12 类攻击，列是 5 层防御；每格不是“预期”，而是真实 defense 类的返回动作。
2. 点 `V02 间接提示注入`：L1 输入层 BLOCK，因为低信任来源里出现了 `SYSTEM:` 指令。
3. 点 `V05 工具调用重定向`：L2 工具白名单 BLOCK，因为 `search` 的 `endpoint` 指向外部。
4. 点 `V07 输出外泄`：L3 输出层是 MODIFY（脱敏），不是 BLOCK；攻击被削弱但仍到达输出。
5. 点 `V09 女巫代理`：只有 L4 FLAG，没有 BLOCK；这是标记，不是拦截。
6. 点 `V12 组合攻击`：expected 的 `behavior_audit` 没被本 harness 行使，但被 output/constitutional 接住；
   `expected_miss` 在页面上明写，不藏。

## 真实与模拟

| 类别 | 说明 |
|---|---|
| 真实 | 攻击 payload 来自 `data/attack_vectors.json`；每格由 `defenses/` 下的真实类检查 |
| 模拟 | 脚本化响应模拟一个会中招的目标；攻击语料是合成的；不是真实 LLM target |

## 文件

```text
demo/
├── harness.py            # 12 条攻击 × 5 层的真实 defense 调用
├── build_static.py       # 生成 public/matrix.json
├── server.py             # stdlib HTTP，静态页 + /api/run
├── public/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── config.json
│   └── matrix.json
├── test_demo.py
└── README.md
```

## 边界

- 这是层内覆盖矩阵，不是端到端多代理运行；单代理 orchestrator 的路由是另一条路径。
- `FLAG` 只表示被标记，不等于 `BLOCK`；V09 在本矩阵里只有 flag。
- V12 的 expected `behavior_audit` 没有被本 harness 行使；它被 output/constitutional 接住。
- 训练/生产环境的真实 block rate 需要接真实 LLM target 后重测。
- `matrix.json` 不参与 `worktree_dirty` 判断。
