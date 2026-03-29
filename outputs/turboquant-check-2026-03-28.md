# TurboQuant Integration Check — 2026-03-28

## TL;DR

TurboQuant is real, it works, and there's already an **Apple Silicon MLX implementation** you can test today. Ollama doesn't have native support yet, but the llama.cpp ecosystem is moving fast. This is worth acting on soon.

---

## What's New (This Week)

TurboQuant dropped publicly on ~March 25, 2026 via Google Research blog. It's being presented at ICLR 2026. The internet lit up — Tom's Hardware, VentureBeat, TechCrunch (they're calling it "Pied Piper"), and a wave of community implementations followed within days.

**Core claims confirmed:** 6x KV cache memory reduction, up to 8x faster attention, 3-bit quantization, zero accuracy loss on Llama-3.1-8B and Mistral-7B.

---

## Integration Status by Ecosystem

### llama.cpp
- **Discussion thread open:** [ggml-org/llama.cpp Discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)
- **Feature request filed:** [Issue #20977](https://github.com/ggml-org/llama.cpp/issues/20977)
- **Working fork exists:** [ikawrakow/ik_llama.cpp Issue #1509](https://github.com/ikawrakow/ik_llama.cpp/issues/1509) — CPU implementation with 18/18 tests passing, MSE matching the paper within 1%. CUDA kernels written, awaiting GPU validation.
- **turboquant_plus project** reports a llama.cpp/Metal integration on Apple Silicon with `turbo3` and `turbo4` KV-cache types, prefill throughput at q8_0 parity, ~4.6x KV cache compression.
- **NOT merged upstream yet.** Still in discussion/PR phase.

### Ollama
- **No native support yet.** Ollama inherits from llama.cpp, so it won't land until llama.cpp merges it upstream.
- Once llama.cpp merges TurboQuant, expect Ollama support within a release cycle or two.

### Apple Silicon / MLX (Most Relevant for M2 Max)
- **turboquant_mlx** — [GitHub repo](https://github.com/helgklaizar/turboquant_mlx): Full MLX-native implementation. 1-3 bit KV cache compression, PolarQuant + QJL, OpenAI server compatible.
- **M2-specific optimization:** A 4-mag LUT auto-detected on pre-M5 devices gives **+38% decode speed on M2 Pro at 8K context**.
- Drop-in replacement for mlx_lm — two lines of code to integrate with existing MLX models.
- **HuggingFace model available:** [flovflo/turboquant-mlx-qwen35-kv](https://huggingface.co/flovflo/turboquant-mlx-qwen35-kv)

### HuggingFace / Python
- **`turboquant` PyPI package** exists — drop-in HuggingFace KV cache replacement. `pip install turboquant`, import `TurboQuantCache(bits=4)`, pass to generation.
- 4-bit recommended as sweet spot for <8B models; 3-bit best for 8B+.

### vLLM
- Feature request filed: [vllm-project/vllm Issue #38171](https://github.com/vllm-project/vllm/issues/38171). No merge yet.

---

## What This Means for OpenClaw (M2 Max, 96GB)

**Potential impact is massive.** Your 14-model stack totals ~264GB local storage, and KV cache is one of the main memory bottlenecks during inference. With TurboQuant:

- **Longer context windows** on existing models without running out of unified memory
- **Run larger models simultaneously** — KV cache freed up = more room for model weights
- **Faster inference** on attention-heavy tasks (trading brain LLM calls, research synthesis)

**Recommended action path:**

1. **Test now (MLX route):** Try `turboquant_mlx` with one of your lighter models (qwen2.5:7b or llama3.2:3b) via MLX. The M2-specific optimizations are already baked in.
2. **Watch llama.cpp:** Star [Discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969) and [Issue #20977](https://github.com/ggml-org/llama.cpp/issues/20977). Once merged, Ollama support follows.
3. **Google official code:** Expected Q2 2026. This will likely accelerate all downstream integrations.
4. **Don't wait for Ollama** — the MLX path is usable today and specifically optimized for your hardware.

---

## Key Links

- [Google Research Blog](https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/)
- [llama.cpp Discussion](https://github.com/ggml-org/llama.cpp/discussions/20969)
- [llama.cpp Feature Request](https://github.com/ggml-org/llama.cpp/issues/20977)
- [turboquant_mlx (Apple Silicon)](https://github.com/helgklaizar/turboquant_mlx)
- [turboquant PyPI](https://pypi.org/project/turboquant/)
- [HuggingFace Paper](https://huggingface.co/papers/2504.19874)
- [Tom's Hardware Coverage](https://www.tomshardware.com/tech-industry/artificial-intelligence/googles-turboquant-compresses-llm-kv-caches-to-3-bits-with-no-accuracy-loss)
- [VentureBeat Coverage](https://venturebeat.com/infrastructure/googles-new-turboquant-algorithm-speeds-up-ai-memory-8x-cutting-costs-by-50)

---

*Next check: Watch for llama.cpp upstream merge and Google's official Q2 release.*
