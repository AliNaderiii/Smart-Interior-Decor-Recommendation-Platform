# API Reference

Base URL: `/api/v1`. Interactive OpenAPI: **`/docs`** (Swagger) and `/redoc`.
Export the spec: `curl http://localhost:8000/openapi.json > docs/openapi.json`.

All responses use the envelope `{ "success": bool, "data": …, "error": string|null }`.
Auth: `Authorization: Bearer <access_token>` (HS256, 15 min; refresh 7 days).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | `{email, password, full_name?, role: homeowner\|designer}` → user + token pair |
| POST | `/auth/login` | → user + token pair |
| POST | `/auth/refresh` | rotates refresh token (old one blacklisted in Redis) |
| POST | `/auth/logout` | blacklists presented refresh token |
| GET | `/auth/me` | current user incl. subscription flags |

## Users (GDPR)
| DELETE | `/users/me` | hard-deletes the user and ALL owned data (audit rows pseudonymised; ADR-014 behavioural rows keep the aggregate history with `user_id` severed) |
| GET | `/users/me/export` | GDPR Art. 15/20 inventory — account, quizzes, moodboards, projects, product_feedback, `behavioural_events` (ADR-014), payments, security_events; 5/hour |

## Quiz & Recommendations
| POST | `/quiz` | validated quiz (styles⊆taxonomy, budget_max>min) → saved with embedding |
| GET | `/quiz`, `/quiz/{id}` | own quizzes |
| POST | `/recommend` | body = inline quiz **or** `?quiz_id=`; 3-stage engine; Redis-cached 1 h; free users get rank-1 full + ranks 2-5 as locked teasers; each product carries `final_score` + `explanation{style_match,color_match,budget_fit,material_match,pattern_match,fit_match,fit_reason,matched_materials,summary}` — `fit_reason` is a stable code (`fit_unknown\|fit_neutral\|fit_ok\|fit_tight\|fit_too_big\|fit_too_small\|fit_too_tall`, ADR-012) |

## Visual search (ADR-013)
| POST | `/search/visual` | multipart `file` (JPEG/PNG/WebP ≤ 8 MB) + optional `?category=<taxonomy id>&limit=1..24`; any signed-in user, 10/min; photo processed in memory, never stored. Returns `items[]` (product payload + `similarity`, `palette_match`, `clip_similarity` in clip mode; free users: top hit per category full, rest `locked` teasers), `is_pro`, and `meta{mode: "clip"\|"palette", palette[], category, candidates, embedding_backend, query_image}` |

## Behavioural events (ADR-014)
| POST | `/events` | `{session_id: 32-hex, events: [{product_id, event_type, page_context, position?, quiz_id?, weights_version?}]}` (≤ 100); closed vocabularies (422 otherwise); signed-in **or** anonymous (forged token → 401); 60/min; **always 202** `{accepted, dropped}` — analytics never fails a user request |
| GET | `/admin/events/summary?days=30` | admin; per-category funnel (`impression, click, like, dislike, save, purchase_click`, `ctr`/`like_rate`/`save_rate` = per impression, `null` without a denominator), `sessions`, `learning_ready` (≥ 10 000 events) |

## Moodboards
| POST/GET | `/moodboards` | items = `[{product_id,x,y,w,h}]` (react-grid-layout), `shopping_list` = product ids |
| GET/PATCH/DELETE | `/moodboards/{id}` | GET embeds referenced product payloads |

## Products (admin only)
| GET | `/products?category=&is_verified=&page=` | paginated |
| POST | `/products` | create; embedding recomputed; seller link checked in background |
| POST | `/products/upload` | multipart image → storage → AI extraction → unverified draft + extraction preview |
| PATCH | `/products/{id}` | edit features (re-embeds when semantic fields change) |
| POST | `/products/{id}/verify` | human-in-the-loop approval |
| DELETE | `/products/{id}` | |

## Designer (B2B2C)
| GET/POST | `/projects` | designer's client projects |
| GET/DELETE | `/projects/{id}` | includes project quizzes |
| POST | `/projects/{id}/share` | `{quiz_id, send_to_email?, expires_days}` → signed token + `/share/{token}` URL, optional email |
| GET | `/share/{token}` | **public, read-only** full recommendations |

## Subscriptions & Payment
| GET | `/subscriptions/me` | plan, active, expiry, Pro price |
| POST | `/payment/request` | creates intent → gateway `redirect_url` (Zarinpal sandbox/mock) |
| POST | `/payment/verify` | `{authority, status}` → verifies with PSP, activates Pro 30 days |

## Admin
| GET | `/admin/users`, `/admin/subscriptions`, `/admin/stats`, `/admin/taxonomy` |
| PATCH | `/admin/users/{id}` | toggle active / change role |

## Health, readiness and metrics

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | Liveness only; returns `200` when the process is running and does not require database or Redis access. |
| GET | `/api/v1/health/ready` | Readiness; checks PostgreSQL with `SELECT 1` and the shared Redis with `PING`. Returns `200` only when both are available, otherwise `503` with `checks.database` and `checks.redis`. |
| GET | `/metrics` | Prometheus text exposition. Includes request counters, latency histograms, in-flight requests, `redis_up`, and static `app_info`; it deliberately has no user, email, token, or route-id labels. Set `METRICS_ENABLED=false` to disable it. |

Every response from the API carries `X-Request-ID`. A valid incoming `X-Request-ID` (letters, numbers, `.`, `_`, or `-`, up to 64 characters) is echoed; invalid or missing values are replaced with a generated identifier. Include this value when reporting an incident so it can be correlated with structured application logs.

Interactive `/docs`, `/redoc`, and `/openapi.json` are enabled outside production. They are disabled by the application in production; expose the API through the Caddy HTTPS proxy and keep `/metrics` restricted to the monitoring network.
