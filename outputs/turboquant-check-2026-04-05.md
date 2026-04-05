# TurboQuant Integration Check — 2026-04-05

**Status:** Active community development, not yet merged upstream. Action items below.

---

## What's New Since Last Check

TurboQuant (Google Research, ICLR 2026) was published March 24, 2026. It compresses KV cache from 16-bit to 3-4 bits per element — roughly 4-6x memory reduction with negligible quality loss. No retraining or calibration needed.

---

## llama.cpp Status

- **Discussion #20969** is the main tracking thread for TurboQuant integration.
- **Feature Request Issue #20977** is open requesting official support.
- **turboquant_plus** (TheTom) has a working C + Metal implementation integrated into llama.cpp with `--cache-type-k turbo3 --cache-type-v turbo3` flags. Validated on Apple Silicon. **Not merged upstream.**
- **ik_llama.cpp Issue #1509** has a separate working implementation (CPU + CUDA) with 18/18 tests passing and MSE matching the paper within 1%.
- A 6-phase integration spec exists covering GGML type registration, KV cache write/read paths, flash attention integration, and CLI flags.

**Bottom line:** Two independent implementations exist. Neither is merged into mainline llama.cpp yet. The turboquant_plus fork is the most relevant for your M2 Max (Metal kernels).

---

## Ollama Status

- **Issue #15051** requests native TurboQuant + RotorQuant in ollama-go-engine.
- **Issue #15189** tracks TurboQuant-MoE (8.5x compression variant).
- No native Ollama support yet. Ollama tracks llama.cpp upstream — once llama.cpp merges TurboQuant, Ollama will follow automatically.
- Community experimental integration exists with custom GGML kernels, reporting 25-28% better compression than Q4_0.

**Bottom line:** Waiting on llama.cpp merge. No action needed on Ollama side yet.

---

## HuggingFace / Python Ecosystem

- **`pip install turboquant`** — community drop-in for HuggingFace's KV cache (back2matching/turboquant).
- **scos-lab/turboquant** — reference implementation reproducing the paper, integrated with HF transformers.
- **tonbistudio/turboquant-pytorch** — from-scratch PyTorch implementation, 5x compression at 3-bit with 99.5% attention fidelity.
- Google's official implementation expected **Q2 2026**.

---

## Apple Silicon / M2 Max Relevance

This is the big one for your setup:

- **turboquant_plus** has native Metal kernels. Compresses KV cache 3.8–6.4x across turbo2/turbo3/turbo4 formats.
- **M2 benchmarks:** ~1% perplexity increase over q8_0, prefill speed maintained (2747 vs 2694 tok/s).
- **Practical impact for 96GB M2 Max:** Could enable 128K context windows on models that currently max out at 32K-64K. Your 70B models (llama3.1:70b, llama3.3:70b at 42GB each) would see dramatically reduced KV cache memory, allowing longer contexts or running more models concurrently.
- 4-bit is the community-recommended sweet spot (0.997 cosine similarity to FP16).

---

## Recommended Actions

1. **Watch llama.cpp Discussion #20969** — this is where merge decisions will happen.
2. **Star TheTom/turboquant_plus** — most mature Apple Silicon implementation. Consider testing it on your M2 Max with one of your smaller models (qwen2.5:7b) to validate before upstream merge.
3. **Wait for Q2 2026** for Google's official implementation — likely to accelerate upstream adoption.
4. **No need to use the Python/HF packages** — your stack is Ollama/llama.cpp, so the C/Metal path is what matters.
5. **Check back in 2-3 weeks** — the pace of PRs suggests upstream merge could happen April-May 2026.

---

## Key Links

- [llama.cpp Discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)
- [llama.cpp Feature Request #20977](https://github.com/ggml-org/llama.cpp/issues/20977)
- [turboquant_plus (Metal/Apple Silicon)](https://github.com/TheTom/turboquant_plus)
- [Ollama Issue #15051](https://github.com/ollama/ollama/issues/15051)
- [turboquant PyPI package](https://pypi.org/project/turboquant/)
- [Google Research Blog](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/)
- [ik_llama.cpp Implementation](https://github.com/ikawrakow/ik_llama.cpp/issues/1509)
