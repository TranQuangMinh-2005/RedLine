# RedLine

Cây thư mục tham chiếu từ **P-187** (`/Users/minh/Desktop/AIInAction/P-187`).

**Nguồn:** `https://github.com/AI20K-Build-Phase-Cohort-3/P-187.git`
**Nhánh:** `origin/main` @ `73ec069ae3dec93935fd5f08fbf2dc9283a4d8f1` (2026-09-06)

## Bật/tắt guardrail

Guardrail dùng một profile cố định cho mỗi benchmark run. Đổi profile sẽ build và
recreate target container để tránh thay đổi cấu hình giữa chừng:

```bash
make defense-none    # baseline: không bật guardrail
make defense-basic   # input filter + prompt hardening + canary check
make defense-strict  # thêm output filter
```

Kiểm tra profile đang chạy:

```bash
curl http://localhost:8000/health
```

Response `/chat` ghi kèm `defense_profile`, `target_config_hash`,
`guardrail_blocked` và `guardrail_actions` để phục vụ tái lập kết quả.

```
P-187/
│
├── README.md                       # Tài liệu chính
├── PROJECT_DOCUMENTATION.md        # Tài liệu kiến trúc chi tiết
├── WORKLOG.md                      # Nhật ký công việc
├── WORKLOG_draft.md
├── README_goc.md                   # Bản gốc tiếng Việt
├── HomeMatch AI Agent.md           # Spec ý tưởng sản phẩm
├── Makefile                        # run / test / lint / format / typecheck / check / log / clean
├── Dockerfile
├── docker-compose.yml              # db (postgres:16-alpine) + backend, có healthcheck
├── pyproject.toml
├── requirements.txt
├── ruff.toml                       # Lint config
├── uv.lock
├── .env.example                    # Mẫu biến môi trường
├── .gitignore / .dockerignore / .gitattributes
├── test_output.json
│
├── 📁 src/                         # BACKEND
│   ├── main.py                     # FastAPI entrypoint
│   ├── config.py                   # Settings tập trung
│   ├── version.py
│   ├── logging_config.py           # Cấu hình logging
│   ├── cleanup_sellers.py
│   ├── reset_demo_passwords.py
│   │
│   ├── api/
│   │   ├── routes.py
│   │   └── routers/                # Mỗi domain một router
│   │       ├── chat.py             # Endpoint hội thoại
│   │       ├── agent.py
│   │       ├── auth.py
│   │       ├── properties.py
│   │       ├── sellers.py
│   │       ├── marketing.py
│   │       ├── tickets.py
│   │       ├── preferences.py
│   │       └── observability.py
│   │
│   ├── agents/                     # Multi-agent / LangGraph
│   │   ├── graph.py  graph_v2.py   # Định nghĩa graph
│   │   ├── state.py  state_store.py # State management (session)
│   │   ├── coordinator.py  coordinator_v2.py
│   │   ├── orchestrator.py  runtime.py
│   │   ├── router.py  synthesizer.py
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── property_agent.py  financial_agent.py
│   │   ├── lifestyle_agent.py  investment_agent.py
│   │   ├── listing_retriever.py
│   │   ├── nodes/                  # Node của graph, mỗi file một node
│   │   │   ├── router_node.py  property_node.py
│   │   │   ├── financial_node.py  hitl_ticket_node.py
│   │   │   ├── out_of_scope_node.py  example_node.py
│   │   ├── tools/                  # Tool calling
│   │   │   └── example_tool.py
│   │   └── adapters/               # Adapter pattern
│   │       ├── base.py  terminal.py
│   │
│   ├── services/                   # Business logic (tách khỏi API & agent)
│   │   ├── llm.py                  # Wrapper gọi LLM
│   │   ├── rag_service.py  property_rag.py
│   │   ├── embedder.py  vector_store.py
│   │   ├── qdrant_store.py  vector_runtime.py
│   │   ├── property_indexer.py  requirement_resolver.py
│   │   ├── rate_limit.py           # Rate limiting
│   │   ├── auth.py
│   │   ├── observability.py
│   │   ├── ticket_service.py
│   │   ├── geo_service.py  spatial.py
│   │   ├── web_search.py  polish.py
│   │   └── description_utils.py
│   │
│   ├── models/
│   │   ├── db.py                   # SQLAlchemy models
│   │   ├── property.py
│   │   └── schemas.py              # Pydantic request/response
│   │
│   └── ingestion/
│       ├── seed_data.py            # Nạp dữ liệu mẫu
│       └── index_properties.py     # Đánh index vào vector store
│
├── 📁 eval/                        # ĐÁNH GIÁ (tách hẳn khỏi src/)
│   ├── run_benchmark.py
│   ├── run_golden_100.py
│   ├── run_eval_evidence_generator.py
│   ├── eval_ragas.py  eval_retrieval.py  eval_extraction.py
│   ├── failure_analysis.py         # Phân tích lỗi
│   ├── golden_dataset.json         # Ground-truth
│   ├── golden_dataset_100.json
│   ├── sample_bds.csv  sample_partner.json
│   └── results/                    # Output, giữ lại làm bằng chứng
│       ├── benchmark_results.json
│       ├── golden_100_report.md
│       ├── ragas_results.json
│       ├── retrieval_results.json
│       ├── extraction_results.json
│       ├── manual_e2e_llm_evidences.json
│       └── report.md
│
├── 📁 tests/                       # Kiểm thử
│   ├── conftest.py
│   ├── test_agents/
│   │   ├── test_graph.py  test_graph_v2.py
│   │   ├── test_orchestrator_v2.py  test_synthesizer.py
│   │   ├── test_pii_guards.py
│   │   ├── test_ticket_service.py
│   │   └── … (22 file test cho agents)
│   ├── test_api/
│   │   ├── test_routes.py  test_agent_endpoints.py
│   │   ├── test_auth_and_config.py
│   │   └── test_observability_endpoints.py
│   └── test_*.py                   # Test tích hợp, geo, vector search, …
│
├── 📁 docs/                        # Tài liệu
│   ├── architecture_diagram.md     # Sơ đồ kiến trúc
│   ├── er_diagram.md               # Sơ đồ ER
│   ├── EVALUATION_PLAN.md
│   ├── evaluation.md  eval_evidences.md
│   ├── JOURNAL.md
│   ├── OBSERVABILITY_DASHBOARD_PLAN.md
│   ├── SKILL.md
│   ├── GEOLOCATION_OSM.md
│   ├── HUONG_DAN_TAI_CAU_TRUC_RAGAS_VA_DATASET.md
│   ├── BaoCaoDanhGia_THUC_NGHIEM.html
│   └── guide/                      # Cẩm nang dạng site
│       ├── chapter-01.md … chapter-10.md
│       ├── setup/        (_index.md, quick-start.md)
│       ├── architecture/ (_index.md, system-design.md)
│       ├── langgraph/    (_index.md, state.md, nodes-and-edges.md, tools.md)
│       ├── patterns/     (_index.md, rag-pattern.md)
│       ├── testing/      (_index.md, writing-tests.md)
│       ├── code-style/   (_index.md, python.md)
│       ├── devops/       (_index.md, docker-cicd.md)
│       ├── deliverables/ (_index.md, checklist.md)
│       ├── anti-patterns/(_index.md, cohort-1-mistakes.md)
│       ├── resources/    (_index.md, recommended-courses.md, reference-teams.md)
│       ├── bmad/         (_index.md, overview.md)
│       ├── book-media/free-accounts/  (ảnh)
│       ├── troubleshooting.md
│       ├── cost-management.md
│       └── free-accounts.md
│
├── 📁 scripts/                     # Thao tác vận hành
│   ├── setup.sh                    # Cài đặt một lệnh
│   ├── setup_hooks.sh / .ps1       # Cross-platform
│   ├── deploy.sh / .ps1
│   ├── run_cli.py  build_golden_100.py
│   ├── generate_bds_data.py  download_media.py
│   ├── cleanup_observability.py  reset_demo_passwords.py
│   ├── log_hook.py  log_manual.py  log_antigravity.py  submit_log.py
│   └── _pyrun.sh / _pyrun.cmd      # Helper chạy python đa nền tảng
│
├── 📁 data/                        # Dữ liệu
│   ├── cleaned/       (.jsonl)
│   ├── media/
│   └── normalized/    (.jsonl)
│
├── 📁 frontend/                    # Next.js App Router
│   ├── package.json  next.config.js  jsconfig.json
│   ├── README.md
│   ├── BAO_CAO_TONG_KET_BASELINE.md
│   ├── PLAN_BASELINE_BDS_VIETNAM.md
│   ├── design-system/homematch/MASTER.md
│   ├── public/         (ảnh, font, icon, manifest, service worker)
│   ├── scripts/warmup.mjs
│   └── src/
│       ├── app/                    # Route-based
│       │   ├── page.js  layout.js  globals.css
│       │   ├── advisor/  grid/  property-detail/  buy/  pricing/
│       │   ├── admin/              (dashboard, agents, properties, observability…)
│       │   ├── seller/             (properties, marketing, profile, tickets)
│       │   ├── auth-login/  auth-signup/  auth-reset-password/
│       │   ├── blogs/  blog-detail/  faqs/  contactus/  aboutus/
│       │   ├── privacy/  terms/  offline/  features/  media/
│       │   ├── components/         # UI components
│       │   │   ├── ChatbotWidget.js  FloatingChatWidget.js
│       │   │   ├── _shared/        (PropertyCard, ThemeToggle, …)
│       │   │   └── …
│       │   └── assets/             (scss, fonts, css)
│       └── lib/
│           ├── api/                (auth, chat, client, properties, sellers…)
│           ├── hooks/  context/  format/  i18n/  mock/
│           └── markdown.js
│
├── 📁 extension/                   # Chrome Extension (Marketing Copilot)
│   ├── manifest.json
│   ├── background.js  content.js  bridge.js
│   ├── popup/          (popup.html, popup.css, popup.js)
│   └── icons/          (16, 48, 128)
│
├── 📁 presentation/
│   ├── HOMEMATCH_PITCH_DECK.pdf
│   └── README.md
│
├── 📁 scratch/                     # Thử nghiệm, không phải production
│   ├── test_geo.py
│   └── test_live_chat.py
│
├── 📁 .github/
│   ├── workflows/ci.yml            # CI/CD
│   └── hooks/hooks.json
│
├── 📁 .agents/                     # Rules & workflow cho AI agent
│   ├── rules/ai-log-hook.md
│   └── workflows/log.md
│
├── 📁 .ai-log/                     # Log phiên làm việc với AI
├── 📁 .claude/   settings.json     # Cấu hình theo từng AI tool
├── 📁 .codex/    hooks.json
├── 📁 .cursor/   hooks.json
└── 📁 .gemini/   settings.json
```
