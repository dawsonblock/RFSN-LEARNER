# RFSN Kernel + Learner

<div align="center">

![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

**A minimal, honest agent backbone with hard boundary architecture**

*Gate never executes. Gate never learns. Gate just says yes or no.*

</div>

---

## Overview

RFSN is a **safety-first execution harness** that separates:

- 🧠 **Reasoning** (untrusted LLM proposals)
- 🔒 **Authority** (deterministic gate decisions)  
- ⚡ **Execution** (trusted tool dispatch)

```
┌─────────────────────────────────────────────────────────────┐
│                    Chat/Reasoning Plane                     │
│  (LLM generates proposals - UNTRUSTED)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ ProposedAction
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     Kernel Plane                            │
│  gate() → allow/deny    ledger.append() → hash chain        │
│  (NO I/O, NO LEARNING - AUTHORITATIVE)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ if allowed
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   Controller Plane                          │
│  tool_router → filesystem, memory, browser                  │
│  (TRUSTED EXECUTOR)                                         │
└─────────────────────────────────────────────────────────────┘
```

## Features

| Component | Description |
|-----------|-------------|
| **Gate** | Pure policy enforcement - no side effects |
| **Ledger** | Append-only hash-chained audit trail |
| **Planner** | Hierarchical goal decomposition with strategy learning |
| **Tools** | Filesystem, memory (SQLite), browser |
| **Learner** | Thompson sampling over candidates and strategies |

## Quick Start

```bash
# Clone
git clone https://github.com/dawsonblock/RFSN-LEARNER.git
cd RFSN-LEARNER

# Demo mode (non-interactive)
python -m controller.chat --demo

# Interactive mode (permissive)
python -m controller.chat --dev

# Hierarchical planning
python -m controller.chat --dev
> /plan list files and then read the README
```

## Project Structure

```
├── rfsn/                    # Kernel (authoritative)
│   ├── gate.py              # Pure policy enforcement
│   ├── ledger.py            # Append-only hash chain
│   ├── policy.py            # Tool allowlists, path constraints
│   ├── types.py             # StateSnapshot, ProposedAction, etc.
│   └── crypto.py            # Deterministic hashing
│
├── controller/              # Trusted executor
│   ├── chat.py              # Interactive CLI
│   ├── agent_gate.py        # Extended gate with policy checks
│   ├── tool_router.py       # Action dispatcher
│   ├── planner/             # Hierarchical planning
│   │   ├── types.py         # PlanStep, Plan, PlanResult
│   │   ├── decomposer.py    # Goal → subtasks
│   │   ├── generator.py     # Strategy selection
│   │   └── executor.py      # Step-by-step execution
│   └── tools/               # Tool implementations
│       ├── filesystem.py    # read, write, list, search
│       ├── memory.py        # SQLite store/retrieve
│       └── browser.py       # fetch_url
│
└── upstream_learner/        # Learning (proposal space only)
    ├── bandit.py            # Thompson sampling
    ├── propose.py           # Candidate & strategy selection
    └── outcome_db.py        # SQLite outcomes
```

## Design Principles

1. **Hard Boundary** - Gate is pure function, no I/O
2. **Immutable Audit** - Every decision hash-chained
3. **Learn in Proposal Space** - Never in authority domain
4. **Fail Safe** - Unknown actions → deny

## Planning Strategies

| Goal Pattern | Strategy | Steps |
|--------------|----------|-------|
| `list files` | `direct` | 1 |
| `X and then Y` | `decompose` | 2-3 |
| `analyze project` | `search_first` | 2+ |
| `help me` | `ask_user` | 1 |

## License

MIT
