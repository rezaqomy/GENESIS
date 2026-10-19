# Cognition and memory

Laya is the default decision provider in infinite worlds. Genesis self-hosts the official [Convai Innovations multilingual checkpoint](https://huggingface.co/convaiinnovations/laya-multilingual) with [Laya's SDK](https://github.com/NandhaKishorM/laya). This is a typed decision model, separate from Ollama: it ranks available goals and returns a choice and probability, without generating prose. The pinned checkpoint revision is `1720e3e3357cfe1e281542e223f8273b0890ca34`, and the SDK is `laya==0.4.7`.

The simulation supplies physiology, personality, emotions, recent memories, learned preferences, weather, home distance, visible companions and community reserves. Only available goals enter the choice schema. The model chooses the goal; UtilityPolicy maps that goal to a current legal movement, harvest, interaction or construction action. Hunger at 85+ and energy below 12 retain deterministic survival priority. Finite legacy worlds retain RulePolicy.

## Primary Laya decisions

At each tick, copied observations enter one bounded background batch. The local service groups equal legal-choice schemas and runs SDK batches of at most four states, on CPU with four threads. The synchronous engine never waits for inference and the model cannot mutate the world.

Each actor's last Laya goal keeps directing freshly planned actions between responses. Results expire after 80 ticks, are discarded on reset, and cannot select currently unavailable goals. A new model choice respects the existing six-tick goal commitment while that goal remains valid; emergencies, three repeated failures or commitment expiry permit switching. This allows most routine actions to follow Laya after initial warmup, rather than using a model result for just one tick. Missing, expired, invalid or emergency decisions use deterministic utility. `GENESIS_COGNITION_INTERVAL=1` allows a new batch after the preceding one finishes; increasing this interval reduces refresh frequency. At high simulation speeds, CPU results can lag and fallback use can rise.

`/api/cognition` reports the actual provider/checkpoint, pending batches, completed model choices, consumed decisions, total decisions, fallback count and error categories. `consumed / decisions` measures the share of actions planned from model goals, including reuse between refreshes; it does not count independent forward passes. Laya's returned probability appears in the inspector's last decision note. It is a model score, not a validated accuracy estimate for this simulation; domain evaluation and fine-tuning remain useful.

## CPU setup

`make dev` installs `.venv-laya` with CPU-only PyTorch and the pinned Laya SDK, then starts the local service on 127.0.0.1:11437 if needed. First startup downloads the checkpoint from Hugging Face; later launches reuse its cache. The backend has its own `.venv`, so Laya's Torch/Transformers/FastAPI dependencies cannot replace the simulation's dependencies. A service started by the development script stops on exit; an existing service is retained.

```sh
make install-laya
.venv-laya/bin/uvicorn scripts.laya_server:app --host 127.0.0.1 --port 11437
```

The service exposes `/health`, `/decide` and `/decide-batch`. Health reports `device=cpu`, checkpoint and revision. `.env.example` provides `GENESIS_DECISION_PROVIDER=laya`, `GENESIS_LAYA_URL`, `GENESIS_LAYA_MODEL`, and `GENESIS_LAYA_REVISION`. For another checkpoint, change both the model and its revision. `GENESIS_COGNITION=0` disables inference while retaining experience memory.

Docker: `GENESIS_COGNITION=1 docker compose --profile cognition up --build` starts the CPU Laya service and preserves its Hugging Face cache in `genesis-laya`. First model load may take several minutes; the world uses fallback until the service becomes ready. The Compose configuration was validated locally; the new Laya Docker image has not been built in this workspace.

## Optional Ollama provider

Qwen and Llama remain installed as alternative local generators. Set `GENESIS_DECISION_PROVIDER=ollama`, and choose `GENESIS_LOCAL_MODEL=qwen2.5:0.5b` or `llama3.2:1b`, then restart the backend. `make dev` starts CPU Ollama on 127.0.0.1:11435 when this provider is selected. The optional provider uses individual structured-output requests, fair scheduling and one active request at a time.

```sh
./scripts/local-models.sh
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen2.5:0.5b
OLLAMA_HOST=127.0.0.1:11435 ollama pull llama3.2:1b
```

If daemon networking fails but curl reaches the registry, `python3 scripts/pull-local-models.py` downloads official manifests/blobs into Ollama's cache with SHA-256 and size verification.

## Dialogue, experience and replay

Dialogue uses only the separately configured OpenAI-compatible provider. Set `GENESIS_DIALOGUE_URL` with its `/v1` base URL, `GENESIS_DIALOGUE_MODEL`, and optional `GENESIS_DIALOGUE_API_KEY`. A local choice to socialize with an adjacent visible companion requests speech. No provider is configured by default, so ordinary socializing works without generated dialogue. A moved/dead listener cannot receive an utterance; speech is delivered once, even when the model goal is reused.

Agents now retain 24 short-term experiences (48-tick lifetime), 64 salient long-term episodes, 64 timestamped food observations (240-tick lifetime), and 32 context-specific practical lessons. Routine movement is sampled every 12 ticks; repeated local movement failures temporarily redirect paths. Actual action effects provide learning feedback; after repeated attempts, deterministic statistical reflections consolidate lessons. Goal adjustments are bounded and never bypass emergency or physical validation. Both providers receive at most six deduplicated recalled episodes and bounded facts/lessons. The legacy 48-experience journal remains readable. The inspector exposes each memory layer, outcomes and evidence counts. See [research, rationale and limitations](agent-memory-research.fa.md). Laya's note reports its typed choice/probability, not an invented chain of thought.

`COGNITION_CONSUMED`, `DIALOGUE` and agent after-images persist decisions, memory and preferences. Replay applies recorded mutations without invoking any model. New optional fields remain absent from canonical historical states until assigned, preserving existing finite/infinite logs. Seed-only reproducibility applies with cognition disabled; model-enabled runs must replay their event logs.

Both providers also receive a bounded summary of the current multi-stage task and three recently updated verified strategies. Task stages are selected again against current legal candidates; emergency survival retains priority. The writer verifies complete-task outcomes from physical state, then stores at most eight results and eight contextual strategies per agent. Only successful recipes create strategies; subsequent failures weaken their utility contribution. These are fixed typed recipes with empirical statistics, not model-generated executable skills. The Plans inspector exposes this evidence. Automatic movement coordination reserves one next tile and records detours/yields without changing stable action resolution order. See [similar-project research](similar-projects.fa.md) and [behavior evaluation](planning-evaluation.fa.md).
