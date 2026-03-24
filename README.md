# VDBFuzz

VDBFuzz is a fuzzing framework for vector databases. It supports Qdrant, Weaviate, and Milvus.

The repository already provides generated test templates under `templates/`, so the normal artifact workflow is:

1. start the target VDB service
2. run fuzzing directly from the provided templates
3. optionally collect new traffic logs and regenerate templates

## Installation

Use Python 3.8+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Optional extras:

```bash
python -m pip install -e ".[capture]"
python -m pip install -e ".[capture,weaviate]"
```

Shortcuts:

```bash
make install
make install-capture
make install-full
```

## Start Local Services

```bash
cp .env.example .env
make vdb-up
```

Default local endpoints:

- Qdrant: `http://127.0.0.1:6333`
- Weaviate: `http://127.0.0.1:18080`
- Milvus REST: `http://127.0.0.1:9091`

Stop services:

```bash
make vdb-down
```

## Run Fuzzing With Provided Templates

This is the main way to run the artifact. The repository already contains ready-to-use templates in:

- `templates/qdrant/`
- `templates/weaviate/`
- `templates/milvus/`

Run fuzzing as follows.

### Qdrant

```bash
python -m vdbfuzz.run \
  -i templates \
  -o output/qdrant \
  -t http://127.0.0.1:6333 \
  -vdb qdrant \
  -n 10 \
  --reset-history
```

### Weaviate

```bash
python -m vdbfuzz.run \
  -i templates \
  -o output/weaviate \
  -t http://127.0.0.1:18080 \
  -vdb weaviate \
  -n 10 \
  --reset-history
```

### Milvus

```bash
python -m vdbfuzz.run \
  -i templates \
  -o output/milvus \
  -t http://127.0.0.1:9091 \
  -vdb milvus \
  -n 10 \
  --reset-history
```

Useful options:

- `-n, --iterations`: mutation iterations per template
- `-p, --parallel`: run templates in parallel
- `-w, --workers`: number of workers in parallel mode
- `-l, --time-limit`: time limit in minutes, `0` means unlimited
- `--reset-history`: rerun all templates instead of skipping previously executed ones

Fuzzing outputs are written to `output/<vdb>/` and include:

- `logs/`: per-template execution logs
- `executed_tests_history.json`: execution history
- `test_report_<timestamp>.json`: summary report

## Generate New Templates From Logs

Template generation is optional. Use it when you want to build new seeds from captured client traffic.

```bash
python -m vdbfuzz.generator \
  -i <log-dir> \
  -o <template-dir> \
  -t <target-url> \
  -vdb <qdrant|weaviate|milvus>
```

Example:

```bash
python -m vdbfuzz.generator \
  -i output/trafficollect/qdrant/http_logs \
  -o output/trafficollect/qdrant/templates \
  -t http://127.0.0.1:6333 \
  -vdb qdrant
```

Generated outputs include:

- `parsed_requests/`: extracted write requests
- `<vdb>/`: generated templates
- `generation_summary.json`: generation summary

## Collect Traffic Logs

Traffic collection helpers are under `vdbfuzz/trafficollect/`.

The recommended path is `HttpCapture` in `vdbfuzz/trafficollect/http_interceptor.py`, which is compatible with the current parser and generator pipeline.

This repository also contains one verified collection example:

- `output/trafficollect/qdrant/http_logs/`
- `output/trafficollect/qdrant/templates/`

## Citation

If you find this repository helpful, please cite our paper:

```bibtex
@inproceedings{wang2026vdbfuzz,
  author = {Wang, Shenao and Liu, Zhao and Zhao, Yanjie and Zou, Quanchen and Wang, Haoyu},
  title = {{VDBFuzz}: Understanding and Detecting Crash Bugs in Vector Database Management Systems},
  year = {2026},
  booktitle = {Proceedings of the 2026 IEEE/ACM 48th International Conference on Software Engineering (ICSE '26)},
  address = {Rio de Janeiro, Brazil},
  doi = {10.1145/3744916.3773139},
  url = {https://doi.org/10.1145/3744916.3773139}
}
```

## Contact

For any questions or support, please contact shenaowang@hust.edu.cn.
