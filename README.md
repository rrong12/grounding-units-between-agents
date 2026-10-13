# Grounding Units Between Agents

Code, data and raw results for **"Bare Numbers Between Agents: Grounding Units and Currencies When Agents Delegate Across
Organisations"**. When a personal agent passes a request such as "my budget is 300,000" to another organisation's agent, the
number arrives intact but its unit or currency often does not. We measure where the convention is lost and evaluate a
grounding protocol (ground, cross-check, read back) against published baselines on conversations from CAPRI.

## Data source and license
The conversations come from CAPRI (Miao, Zhu & Shwartz 2026, "LLMs Infer Cultural Context but Fail to Apply It When
Responding", [arXiv:2606.17688](https://arxiv.org/abs/2606.17688); Hugging Face `yisongmiao/CAPRI`). CAPRI's conversations
and metadata are licensed CC BY 4.0 (`experiments/capri/LICENSE_capri.md`; dataset card in `experiments/capri/README_capri.md`).
We redistribute the processed conversations, with attribution, in `sample.json` (development set), `heldout.json` (held-out
test set) and `full.json` (all conversations), plus CAPRI's `ground_truth_units.json`. No images are included.

## Layout
```
_lib/                     llm.py (OpenRouter client), claude_mcp.py (`claude -p` episodes), codex_mcp.py (`codex exec`
                          episodes), mock_mcp.py (stdio MCP server that serves the experiment's tool and logs its calls)
experiments/capri/        runners: run.py, run_or.py, run_claude.py, run_ablation.py, run_e2e.py, run_probe.py
                          analysis: analyze_frontier.py, analyze_messages.py, analyze_e2e.py
                          data prep: fetch_capri.py (download CAPRI -> full.json), make_split.py (full.json -> heldout.json)
                          harness: harness_env.sh, pipeline.sh (zsh); data and results_*.json(l)
experiments/paper_tables/ make_tables.py; numbers.tex and tables/*.tex are its output, as used in the paper
```

## Reproduce every table and number
Python 3.9+, standard library only, no network:
```
cd experiments/paper_tables && python3 make_tables.py     # rewrites numbers.tex and tables/*.tex
```
`experiments/capri/analyze_*.py` print fuller summaries, for example
`python3 analyze_e2e.py --split heldout --file results_e2e_heldout.jsonl`.

## Which file backs which part of the paper
| Paper | Results file(s) |
|---|---|
| Single agent vs relay, injected sender messages, explicit units (Tables 1-3) | `results_frontier_*.jsonl` (Opus 5.5, Haiku 4.5, Fable 5.1, GPT-6.1, Ling-3.1-Flash), `results_claude_sonnet.json`, `results_ablation.jsonl` |
| Method development and step ablations (Table 5) | `results_e2e_dev.jsonl` |
| Held-out test of the method and baselines (Table 4 and appendix tables) | `results_e2e_heldout.jsonl` |

## Rerun the experiments
Claude models run through the Claude Code CLI: `_lib/claude_mcp.py` calls `claude -p` with the system prompt replaced, no
settings sources, built-in tools off and only `mock_mcp.py` as an MCP server. GPT runs through `codex exec`
(`_lib/codex_mcp.py`), and the open-weight model through OpenRouter (`run_or.py`, which needs a real `OPENROUTER_API_KEY`).
Launch from a plain terminal (zsh), not from inside an agent session:
```
cd experiments/capri && source harness_env.sh
python3 run_e2e.py SENDER RECEIVER CONDS --split dev|heldout [--step K] [--same] [--workers W]
```
`run_e2e.py` appends to `results_e2e.jsonl` by default; set `E2E_OUT` to write elsewhere. The other runners' usage lines are
in their docstrings, and `pipeline.sh` lists the exact command of every stage. All runners are resumable: they append to
their results file and skip finished items.
