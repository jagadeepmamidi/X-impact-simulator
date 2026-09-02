# Colab / dedicated GPU — BluePrint + Nemotron (no live X feed)

SOP datasets. Run these cells in order on the GPU box. Accept gated BluePrint on HF first: https://huggingface.co/datasets/ComplexDataLab/BluePrint

Upload the `training/` folder (or clone the repo) so `phoenix_map.py` is on the path.

---

## Cell 1 — install

```python
%pip install -q datasets huggingface_hub scikit-learn joblib transformers peft accelerate bitsandbytes
```

## Cell 2 — login

```python
from huggingface_hub import login
login()  # paste HF token with access to ComplexDataLab/BluePrint
```

## Cell 3 — path

```python
import sys
from pathlib import Path
ROOT = Path("/content/X")  # change if you cloned elsewhere
sys.path.insert(0, str(ROOT / "training"))
print("ok", ROOT.exists())
```

## Cell 4 — stream BluePrint → Phoenix JSONL (~80k next-action rows)

```python
from prepare_blueprint import prepare
from pathlib import Path
summary = prepare("25_clusters", 80000, Path("/content/blueprint_phoenix.jsonl"), seed=42)
print(summary)
```

Single-message threads are skipped. Labels: favorite, reply, retweet, quote, follow_author, block_author.

## Cell 5 — classical heads (CPU or GPU, minutes)

```python
from train_heads import train
from pathlib import Path
report = train(Path("/content/blueprint_phoenix.jsonl"), Path("/content/artifacts"), split="shuffle")
print(report["beats_majority_ap"])
print(report)
```

Default split is shuffled 90/10 (pass `split="sequential"` only to reproduce the old cut). Download `phoenix_heads.joblib`, `train_report.json`, and `model_card.json` to `training/artifacts/`. Do not ship heads that lose to the majority-class AP baseline.

## Cell 6 — Nemotron persona packs (CC BY 4.0)

```python
from prepare_nemotron import prepare as prep_n
from pathlib import Path
print(prep_n(8, 30000, Path("/content/nemotron_packs"), seed=42))
```

Copy the four `*_nemotron.json` files to `data/processed/nemotron_packs/`. Do not replace production packs until you review IDs.

## Cell 7 — optional QLoRA (only after Cell 5 looks sane)

Do **not** mix Salesforce/SCOPE-Persona (CC BY-NC). BluePrint MIT + Nemotron CC BY 4.0 only.

```python
# Optional. Skip until average_precision per head is inspected.
# Uses a small instruct model to emit Phoenix JSON from post text + cluster_id.
# Keep max_steps low for the first GPU pass.
print("Skip QLoRA until classical AP is reviewed.")
```

Not in this notebook: live For You / Thunder / Phoenix ranker, Kaggle X dumps, SCOPE production training.
