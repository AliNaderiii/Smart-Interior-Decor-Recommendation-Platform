# G-4.x — /recommend p95 evidence (verification run #7)

Source: run [`33334578659`](https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform/actions/runs/33334578659),
job "G-4.x — /recommend p95 against the demo container", commit `7896b2e`.
Both cells measured against the demo **container** (nginx → uvicorn →
PostgreSQL 16 + pgvector + Redis, all in-image) on a GitHub-hosted runner.

Copied verbatim from the job's check-run annotations:

```
p95-cells: n=200/cell conc=20 | cold p50=495.8 p95=701.3 p99=791.0 err=0 | warm p50=72.6 p95=111.2 p99=131.2 err=0 | gate_cold<2000ms cold_pass=True gate_warm<2000ms warm_pass=True
p95-cells: n=250/cell conc=20 | cold p50=486.2 p95=706.4 p99=807.9 err=0 | warm p50=73.0 p95=181.6 p99=232.0 err=0 | gate_cold<2000ms cold_pass=True gate_warm<2000ms warm_pass=True
```

| Cell | n | conc | p50 (ms) | p95 (ms) | p99 (ms) | errors | gate |
|---|---|---|---|---|---|---|---|
| cold | 200 | 20 | 495.8 | **701.3** | 791.0 | 0 | <2000 PASS |
| warm | 200 | 20 | 72.6 | **111.2** | 131.2 | 0 | <2000 PASS |
| cold | 250 | 20 | 486.2 | **706.4** | 807.9 | 0 | <2000 PASS |
| warm | 250 | 20 | 73.0 | **181.6** | 232.0 | 0 | <2000 PASS |

**Worst observed p95: 706.4 ms — 35% of the 2000 ms contract threshold.
Zero failed requests across 900 measured samples.**

## The verdict is PROVISIONAL

This is a **GitHub-hosted shared runner**, which is the hardware class
IR-S3-002 objected to. The measurement is real and the gate genuinely passes,
but it does not close IR-S3-002 — that needs the Stage-5 client-funded host.
The rate limiter was set to `RECOMMEND_RATE_LIMIT_PER_MINUTE=0` on this
container only (the documented load-test switch); the shipped image and
`demo-verify` keep the live limiter.
