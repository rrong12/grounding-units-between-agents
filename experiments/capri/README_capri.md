---
license: other
license_name: mixed-cc
license_link: LICENSE.md
language:
- en
task_categories:
- visual-question-answering
tags:
- pragmatic speaker
- cultural grounding
- multimodal models
pretty_name: CAPRI
---

# CAPRI — Cultural and Pragmatic Response Inference

A multimodal dataset for studying whether LLMs act as a **pragmatic speaker** —
tailoring their answers to the user's perceived cultural background. Each item
is a short conversation between a user and a chatbot with **varying degrees of
cultural cues** about the user's background, followed by a visual question about
an image (e.g., *What is the temperature?*). The model must (1) **infer the
user's cultural background** from the conversation (**BG — Task 1**), and (2)
**adapt its answer to the local units of measurement** (**VQA — Task 2**, the
primary task) — for example, *104 °F* for a US user versus *40 °C* for a French
user. CAPRI thus disentangles *knowing* a user's culture from *acting on it*.

The primary dimension is units of measurement (currency, distance, size,
temperature); we also include two more subjective, culturally-grounded
dimensions — time expressions (*morning*, *afternoon*) and quantity expressions
(*few*, *some*). Each image is presented across **10 cultures** (Brazil, China,
France, India, Iran, Israel, Japan, South Korea, UK, US).

**Size: 172 images · 516 scaffolds · 4,992 implicit + 516 neutral conversations.**

## Dataset Structure

### Statistics

| Type | Dimension | # Images | # Scaffolds | # Conv | Question | Possible Answers |
|------|-----------|---------:|------------:|-------:|----------|------------------|
| **Type 1** — Objective, w/ ground truth | Temperature | 33 | 99 | 990 | What is the temperature? | °C, °F |
| | Distance | 32 | 96 | 864 | What is the distance? | m, km, ft, mi, yd, ... |
| | Speed | 18 | 54 | 540 | What is the speed? | km/h, mph, m/s, ... |
| | Size | 24 | 72 | 648 | What is the room size? | m², ft², ... |
| | Price | 21 | 63 | 630 | What is the price? | USD, EUR, CNY, JPY, ... |
| **Type 2** — Subjective, w/o ground truth | Time Expression | 24 | 72 | 720 | What time is it? | morning, noon, afternoon, evening, night |
| | Quantifiers | 20 | 60 | 600 | What is the quantity? | few, some, half, most, almost all |
| **Total** | | **172** | **516** | **4,992** | | |

### Files

```
conversations/<concept>[/<variant>]/<type>/      conversations by type: implicit / neutral
images/<concept>[/<variant>]/                    images + random_index.json
ground_truth_units.json                          accepted units per culture × concept
country_list.json                                country name variants (Background Inference)
licenses/                                         attribution + per-image license CSVs
```

`<type>` is `implicit` — cultural cues embedded, so **culturally specific** (one
conversation per culture) — or `neutral` — no cues, so **culturally agnostic**
(one shared conversation per item). `<variant>` appears only where a
concept has more than one image source: `time` and `temperature` split into
`camera` (photographed) and `aigen` (AI-generated); `quantifiers` splits into
`battery` and `eggs`.

Example layout:

```
CAPRI/
├── conversations/
│   ├── price/                       # concept with no variant
│   │   ├── implicit/                #   one conversation per culture
│   │   │   ├── ID_10_bg_China_fn_chair1.jpg_full.json
│   │   │   └── ...
│   │   └── neutral/                 #   culturally-neutral scaffold
│   ├── time/                        # concept with an image-source variant
│   │   ├── camera/                  #   photographed
│   │   │   ├── implicit/
│   │   │   └── neutral/
│   │   └── aigen/                   #   AI-generated
│   ├── quantifiers/                 # variant = object set
│   │   ├── battery/
│   │   └── eggs/
│   └── distance/  size/  speed/  temperature/
├── images/
│   ├── price/                       # images + selection index
│   │   ├── chair1.jpg
│   │   └── random_index.json
│   └── time/{camera,aigen}/  ...
├── ground_truth_units.json          # accepted units per culture × concept
├── country_list.json                # country name variants (Background Inference)
├── licenses/
│   ├── ATTRIBUTION.md               # TASL manifest
│   └── {price,speed,temperature,time}.csv
├── LICENSE.md
└── README.md
```

## License and Attribution

Please kindly refer to [LICENSE.md](LICENSE.md).<br>
Our CAPRI conversations and metadata are released under CC BY 4.0.<br>
All images are licensed individually — Flickr Creative Commons photographs,
AI-generated images, and author-made graphics — with full attribution in
[licenses/ATTRIBUTION.md](licenses/ATTRIBUTION.md). We warmly thank the
photographers for sharing their work under permissive Creative Commons licenses.

## Authors & Contact

- Yisong Miao — [email removed]
- Jian Zhu — [email removed]
- Vered Shwartz — [email removed]

## Citation

If you use CAPRI, please cite:

```bibtex
@misc{miao2026capri,
      title={LLMs Infer Cultural Context but Fail to Apply It When Responding}, 
      author={Yisong Miao and Jian Zhu and Vered Shwartz},
      year={2026},
      eprint={2606.17688},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2606.17688}, 
}
```
