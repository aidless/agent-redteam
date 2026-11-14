# --- acceptance_backfill (EVAL_ACCEPTANCE_STANDARD.md P4) ---
# 证据来源: tests/ + .github/workflows/ci.yml
# 命令逐字取自该来源，未增删任何参数。
# 补环境前缀（本机实测）：原 `pytest tests -q` 卡死而非报错——tests/test_v04.py:73
# `test_sentence_transformer_if_available` 直接构造 SentenceTransformerEmbedder()，
# 构造过程要去 huggingface.co 拉模型，本机不可达就阻塞到网络超时（240s timeout 只跑了 36 个点）。
# 加 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 让它在取模型时立刻 OSError → 走测试自己
# 写好的 skip 路径（tests/test_v04.py:86-88），整套变 97 passed / 1 skipped，rc=0。
# 注意：这条 skip 是「本机没有模型缓存」的既有实现，不是为跑绿而加的过滤。
.PHONY: eval

eval:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python3 -m pytest tests -q
