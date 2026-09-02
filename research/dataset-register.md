# Dataset register (SOP §3.2 / §6)

Retrieved 2026-09-02. Pin these IDs before any training run. No live X feed is used.

| Dataset | URL | License | Role | Status |
| --- | --- | --- | --- | --- |
| ComplexDataLab/BluePrint | https://huggingface.co/datasets/ComplexDataLab/BluePrint | MIT (gated) | Next-action labels → Phoenix heads | Research prototype; gated access confirmed for `frozen8569` |
| nvidia/Nemotron-Personas-USA | https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA | CC BY 4.0 | Persona diversity; occupation/hobby routing | Usable with attribution; drop sex/age/marital/zip |
| Salesforce/SCOPE-Persona | https://huggingface.co/datasets/Salesforce/SCOPE-Persona | CC BY-NC 4.0 | Sociopsychological reference | **Do not train production models** |
| Salesforce/RealUserSim | https://huggingface.co/datasets/Salesforce/RealUserSim | ODC-BY | Communication-style eval | Optional; not engagement ground truth |
| Kaggle X engagement | — | TBD | Calibration | Deferred until provenance/license review |
| Creator opt-in analytics | — | User consent | Long-term calibration | Not in this phase |

SIMPACT paper (BluePrint methodology): https://arxiv.org/abs/2510.02343

Cards: `research/datasets/`.
