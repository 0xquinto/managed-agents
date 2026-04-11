# Researcher Agent Pattern

> Research compiled 2026-04-09. Sources: arXiv papers on Deep Research Agents (2506.18096, 2509.13312, 2509.24107, 2602.06540, 2509.00244, 2604.05952, 2602.13855, 2509.04499, 2510.02326, 2507.10522, 2604.06170, 2603.13327, 2601.14351); Claude Lab production guides; V7 Labs CI agent; MarketBetter CI tutorial; SerpAPI competitive intelligence agent (GitHub); BattleBridge multi-agent CI; Octopus Intelligence agentic CI; divar-ir/ai-doc-gen (GitHub, 708 stars); facebookresearch/DocAgent; RepoAgent (arXiv 2402.16667); sarupurisailalith/codebase-cortex; Multi-Agent RAG guides (Ailog, Orq.ai, ZBrain); AutoGenAgents framework (IJCTEC 2025); Evidence Bundle-Enforced RAG (MARIA OS 2026); DeepTRACE audit framework; urlhealth citation tool.

---

## 1. Pattern Definition

The **Researcher** pattern abstracts the operation:

```
Question → [Multi-Source Gathering] → [Synthesis] → Report
```

A researcher agent receives an open-ended question or research brief, autonomously gathers information from multiple heterogeneous sources, reasons across retrieved evidence, and produces a structured report with citations. The key differentiator from a simple RAG lookup is **autonomy over the gathering loop**: the agent decides which sources to query, in what order, and when sufficient evidence has been collected.

**Core invariant:** The question is stated once; the agent determines its own retrieval strategy and iterates until depth/breadth targets are met.

**Distinguishing characteristics vs. other patterns:**
- Unlike a **transformer**, the researcher reads and synthesizes rather than writing or modifying artifacts.
- Unlike a **reactive-pipeline**, the researcher is not event-driven; it runs to completion on a single prompt.
- Unlike a **evaluator**, the researcher produces original synthesis rather than a quality judgment of an existing artifact.
- Unlike basic RAG, the researcher performs multi-hop, iterative retrieval — each retrieved chunk can generate new sub-queries.

**Concrete instances observed in production:**

| Instance | Question Type | Primary Sources | Output |
|---|---|---|---|
| OpenAI Deep Research / Gemini Deep Research | PhD-level open questions | Web crawl, search APIs | Long-form cited report |
| V7 Labs CI Agent | Competitor monitoring brief | Websites, SEC filings, social media | Periodic intelligence briefing |
| BattleBridge 10-agent CI system | Market scanning across 977 cities | Web scrapers, CRM, pricing pages | Daily intel report + Slack alerts |
| SerpAPI competitive intelligence agent | "Brief me on Acme" | SerpApi (web/news/jobs) + HubSpot CRM | Short briefing with numbered citations |
| divar-ir/ai-doc-gen | Codebase understanding | File system (repo contents) | README + CLAUDE.md + AGENTS.md |
| facebookresearch/DocAgent | Per-function documentation | Repo AST, inter-file dependencies | Docstrings for every function |
| RepoAgent | Repository-level docs | Global repo parse + reference graph | Fine-grained hierarchical docs |
| codebase-cortex | Incremental doc sync | Git diffs + semantic search (FAISS) | Updated markdown docs per PR |
| AutoGenAgents (healthcare/finance) | Multi-document synthesis | PDFs, DOCX, HTML, images (OCR) | Structured report with inline citations |
| DOVA platform | Complex research automation | ArXiv, code repos, model registries | Cited synthesis with confidence scores |
| AgentCPM-Report | Open-ended research | Web search, iterative retrieval | Long-form insight-driven reports |

---

## 2. Common Research Types

### 2.1 Deep / Academic Research
Open-ended questions requiring multi-hop reasoning across many sources. Systems: OpenAI Deep Research, Gemini Deep Research, Perplexity Deep Research, WebWeaver, Fathom-DeepResearch, AgentCPM-Report. Benchmark: DeepResearch-Bench (100 PhD-level tasks).

**Architectural signature:** Planner → iterative (Search → Summarize → Update outline) → Writer. Breadth (parallel sub-queries) and depth (recursive follow-up) are explicit parameters. WebWeaver uses a dual-agent planner/writer split with a shared memory bank keyed by outline section.

### 2.2 Competitive Intelligence
Ongoing monitoring of competitor websites, filings, pricing, job postings, and social media. Output is a recurring briefing delivered on a schedule (daily/weekly).

**Architectural signature:** Scheduler → per-competitor crawlers → change detection (diff against snapshot) → LLM relevance scoring → report compiler → delivery (Slack/email/Notion). Stateful: requires baseline snapshots for delta detection. Data tiers: Tier 1 (pricing, product pages — high impact), Tier 2 (job postings, ads), Tier 3 (social, news — context enrichment).

**Key sources by signal type:**

| Signal | Source |
|---|---|
| Pricing changes | Direct scrape of SaaS pricing pages, Shopify APIs |
| Strategic intent | SEC 10-K / 10-Q via EDGAR JSON/XBRL APIs |
| Product launches | RSS feeds, press release monitors |
| Hiring signals | Google Jobs API, LinkedIn scrape |
| Ad strategy | Google Ads Library API (free), Meta Ads Library, LinkedIn Ads |
| Social sentiment | X/Reddit APIs, social listening tools |
| Website messaging changes | Playwright/Puppeteer diff against last snapshot |

### 2.3 Documentation Generation
Agent analyzes a codebase or product and generates structured documentation. Inputs are source files, not web pages.

**Architectural signature:** Multiple concurrent specialist analyzers (structure, dependencies, data flow, request flow, API endpoints) → synthesis agent → documentation writer(s). divar-ir/ai-doc-gen runs 5 analysis agents concurrently then a single README generator. DocAgent uses Reader → Searcher → Writer → Verifier coordination under an Orchestrator, with hierarchical traversal ordered by dependency depth (leaf files first).

### 2.4 Due Diligence / Market Analysis
One-shot deep reports for investment, M&A, or market entry decisions. Combines web research, regulatory filings, financial data, and internal documents.

**Architectural signature:** SambaNova/AI-Q style 5-step pipeline: (1) parse scope, (2) generate outline with section-level planning, (3) gather via web tools + APIs + specialized sub-agents (e.g., financial agent), (4) synthesize into Markdown with citations. Enterprise variants add knowledge graph (ERP AI) or RAG over internal document stores.

### 2.5 Literature / Scientific Research
Systematic review across academic databases. Inputs are PDFs, arXiv, PubMed, Semantic Scholar, ORKG.

**Architectural signature:** PaperCircle-style: discovery pipeline (diversity-aware ranking, structured outputs) + analysis pipeline (ingestion → graph builder → Q&A → verification). Outputs JSON, CSV, BibTeX, Markdown, HTML. Iterative orchestrator alternates noising/denoising passes against an evolving discovery state.

---

## 3. Source Gathering Strategies

### 3.1 Source Taxonomy

| Source Type | Access Pattern | Typical Tools |
|---|---|---|
| Open web | web_search → ranked results; web_fetch → full page | Exa, Tavily, SerpApi, Firecrawl, Playwright |
| Structured APIs | REST/JSON calls with auth | EDGAR API, Google Ads Library, Semantic Scholar API, PubMed Entrez |
| Internal document stores | Vector similarity search (RAG) | FAISS, Milvus, Pinecone, Qdrant; chunked with overlap |
| Relational databases | SQL queries via tool | PostgreSQL, SQLite via agent tool call |
| File system / code repo | File read + AST parse | FileReadTool, ListFilesTool, TreeSitter, PyMuPDF |
| CRM / SaaS integrations | API calls with credentials | HubSpot, Notion, Salesforce |
| Social / news | RSS, social APIs | RSS aggregators, X API, Reddit API |

### 3.2 Parallel vs. Sequential Retrieval

- **Sequential (reactive):** Each search result can spawn the next query. Used in deep research where each hop builds on prior findings. Depth-first exploration of a topic tree. Example: WebWeaver planner loop.
- **Parallel (fan-out):** Sub-queries for independent sections issued simultaneously. Used in competitive intelligence (multiple competitors in parallel) and doc generation (5 concurrent analyzers). Throughput gain when subtasks are truly independent.
- **Hybrid:** Orchestrator decomposes question → fans out parallel searches per sub-topic → sequential refinement within each sub-topic. Most production systems (SambaNova, DOVA, Fathom-DeepResearch) use this pattern.

### 3.3 Query Formulation Strategies

- **Semantic objectives over keywords:** Describe the ideal source page in natural language ("blog post comparing React and Vue performance"), not keyword strings. Exa explicitly recommends this.
- **Objective + search_queries pairing:** Provide both a natural-language objective (context for the task) and specific keyword queries (ensures terms are matched). Parallel.ai's best practice.
- **Sub-goal decomposition:** Break the top-level question into sub-goals before issuing any search. Fathom-Synthesizer-4B uses Plan-then-Write: decompose → map evidence to sections → write with citations strictly from explored URLs.
- **Follow-up question generation:** After summarizing each retrieved document, emit 1-3 follow-up questions that expose gaps. These become next-iteration queries. Used in iterative deep research loops (arXiv 2507.10522).
- **Domain restriction vs. open web:** Use `include_domains` only when answers must come exclusively from specific sources (compliance, internal corpora). For general research, steer via objective text rather than hard domain filters to avoid shrinking the search space.

### 3.4 Memory and State Management

Production systems avoid a single growing context window. Instead:
- **Memory bank / evidence store:** Retrieved chunks stored externally (Redis, Postgres, FAISS), keyed by section ID or claim ID. Writer agent retrieves only relevant evidence per section at write time (WebWeaver).
- **Shared blackboard state:** Agents read/write from a shared task store with task_id, provenance metadata, and intermediate outputs. Enables forensic audit of which source supported which claim.
- **Snapshot baseline (CI agents):** Stateful store (PostgreSQL or flat JSON) holding previous snapshot of each competitor page. Delta detection compares current scrape against stored baseline.

### 3.5 Multi-Agent Specialization

Splitting retrieval from synthesis from validation is the dominant pattern in production-quality researcher systems:

| Role | Responsibility |
|---|---|
| Planner / Orchestrator | Decomposes question, assigns sub-tasks, enforces stop conditions |
| Web Researcher / Retriever | Issues queries, fetches pages, respects URL allowlists / robots.txt |
| Summarizer | Produces concise section-level summaries with inline citations |
| Synthesizer / Writer | Fuses summaries into coherent prose, attaches citation list |
| Critic / Reviewer | Evaluates draft quality, coverage gaps, factual consistency |
| Verifier / Validator | Checks citations against retrieved evidence; runs URL liveness checks |
| Formatter | Applies consistent structure, generates ToC, executive summary, reference list |

---

## 4. Report Quality Controls

### 4.1 Hallucination: What Goes Wrong

Research from urlhealth (arXiv 2604.03173) across 10 commercial models on DeepResearch-Bench found:
- 3–13% of citation URLs are hallucinated (model-invented, never retrieved).
- 5–18% of URLs are non-resolving (hallucinated or stale).
- Deep research agents exhibit **higher** hallucination rates than simpler retrievers — longer context increases fabrication risk.
- Generating more citations per query does not reduce per-citation error rate; it worsens it. Citation volume is not a quality proxy.
- DeepTRACE audit framework found citation accuracy of 40–68% across leading engines: models frequently cite a real but irrelevant source.

### 4.2 Hallucination Mitigation Techniques

**Structural / Architectural:**

1. **Closed-world citation policy:** Citations may only reference IDs of documents actually retrieved by the agent. Fathom-Synthesizer-4B enforces this: citations drawn strictly from URLs explored by Fathom-Search-4B. RA-FSM uses a deterministic citation pipeline where every answer cites only `(doc_id, span_id)` pairs from the vector index.

2. **Evidence Bundle enforcement:** Every claim must carry an evidence bundle (source, paragraph reference, confidence score). If the aggregate evidence falls below a sufficiency threshold, the system refuses to answer rather than hallucinating. Evidence Bundle-Enforced RAG reduces hallucination from 23.7% to 3.2% in controlled enterprise deployments.

3. **Section-level citation constraints:** Map outline sections to their evidence pool before writing. Writer agent receives only the evidence subset for each section, preventing cross-contamination and irrelevant citation.

4. **Progressive confidence estimation:** Decompose report into QA-style sub-claims, each with a verifiable evidence reference and a confidence score. Report surfaces uncertainty at claim granularity rather than as a monolithic output. (arXiv 2604.05952)

5. **URL liveness verification:** Post-generation step checks every cited URL for HTTP liveness. Tool `urlhealth` classifies URLs as LIVE, STALE (archived), or LIKELY_HALLUCINATED (HTTP 404, no archive). In agentic self-correction experiments, URL non-resolving rates drop by 6–79× to below 1% when this tool is in the loop.

6. **Verifier agent in the pipeline:** DocAgent's Verifier role checks generated docstrings against the AST for completeness (parameters, returns, exceptions). AutoGenAgents uses a Reviewer agent for consistency and citation presence checks before output.

7. **Cross-source validation (chain-of-verification):** Retrieve the same fact from ≥2 independent sources. Flag discrepancies rather than smoothing them. Used in OpenAI Deep Research training via RL. Octopus Intelligence recommends Chain-of-Verification and retrieval relevance + answer relevance + groundedness triad (RAGAS evaluation).

**Prompting / Inference-time:**

8. **Low temperature for synthesis:** Summarizer/Synthesizer agents should use temperature 0.0–0.3. Planning agents can use higher temperature for query diversity.

9. **"I don't know" fallbacks:** When confidence is below threshold, agent emits an explicit uncertainty statement rather than a confident claim. RA-FSM implements a finite-state controller that gates answering on a confidence score.

10. **Claim-level provenance graph:** Link every key claim to its evidence with explicit reasoning edges (W3C PROV standard). Enables forensic queries like "which evidence justified framing X as Y?" (arXiv 2602.13855 — Auditable Autonomous Research standard).

### 4.3 Report Structure Patterns

The following structure appears consistently across production research systems:

```
# [Title]

## Executive Summary          ← 3-5 bullet synthesis; written last
## Table of Contents          ← auto-generated by Formatter agent
## [Section 1: Background]    ← contextual framing
## [Section 2-N: Findings]    ← one section per sub-topic; each has inline citations
## Competitive/Risk Analysis  ← optional; present in CI and due-diligence instances
## Recommendations            ← optional; present in market analysis instances
## Appendix / Raw Data        ← optional; supporting tables, raw scraped data
## References                 ← numbered list; [1] Author, Title, URL, Accessed date
```

**Citation format:** Inline numbered footnotes `[1]`, `[2]` linked to a numbered reference list at the end. Each reference includes URL, access date, and (for academic sources) DOI. This matches the format used by SerpAPI competitive intelligence agent, multi-agent research report generators, and arXiv deep research systems.

### 4.4 Iteration Patterns

Three iteration models are observed:

| Model | Description | When Used |
|---|---|---|
| **Static pipeline** | Plan → Gather → Synthesize → Write → Format. Single pass. | Simple questions, doc generation, narrow CI tasks |
| **Depth-first iterative** | Each search result generates follow-up queries until max depth reached. Breadth (b) and depth (d) are parameters. | Deep research, scientific literature review |
| **WARP (Writing As Reasoning)** | Outline and content co-evolve. Writing reveals gaps → agent revises outline → triggers new retrieval. | Open-ended research with insight-ceiling concern |
| **Draft → Critic → Refine** | Writer produces draft → Critic evaluates gaps/accuracy → Writer revises. 1-3 loops. | High-stakes reports, documentation, due diligence |

For managed agents, the **depth-first iterative** model is the most practical starting point: it is parameterizable (set `max_depth` and `max_breadth` to bound cost and time), well-studied, and produces good results across research types.

---

## 5. Recommended Default Configuration

```yaml
# Researcher Agent — default config for Claude Managed Agents orchestrator

name: researcher
description: >
  Gathers information from multiple sources and synthesizes a structured,
  cited report. Supports web research, competitive intelligence, codebase
  documentation, and multi-document synthesis.

model: claude-sonnet-4-6          # balance of reasoning quality and cost
max_tokens: 16000                 # long-form reports require headroom

tools:
  - web_search                    # primary retrieval: Exa / Tavily / SerpApi
  - web_fetch                     # full-page content extraction from URLs
  # Optional, enable per use case:
  # - file_read                   # for codebase documentation instances
  # - list_files                  # for codebase documentation instances
  # - run_sql                     # for structured database sources
  # - vector_search               # for internal document stores (RAG)
  # - http_get                    # for structured APIs (EDGAR, HubSpot, etc.)

networking: unrestricted          # web_search and web_fetch require open egress
                                  # CI agents also need access to competitor domains

memory:
  type: external                  # never rely solely on context window
  backend: redis                  # or postgres; stores evidence chunks keyed by section_id
  snapshot_store: postgres        # for CI agents: baseline snapshots for delta detection

agent_roles:                      # recommended decomposition for complex tasks
  planner:
    prompt: decompose question into sub-goals and assign to retriever
    temperature: 0.7              # diversity in query generation
  retriever:
    prompt: execute searches; return (url, snippet, confidence) tuples
    temperature: 0.2
    max_tool_calls: 30            # bound per-run cost; tune by depth setting
  summarizer:
    prompt: produce 150-300 word summary with inline citations per section
    temperature: 0.1
  synthesizer:
    prompt: fuse section summaries into coherent prose; cite only retrieved URLs
    temperature: 0.2
    citation_policy: closed_world # citations restricted to retriever-explored URLs only
  verifier:
    prompt: check URL liveness; flag hallucinated or stale references
    tools: [url_health_check]
  formatter:
    prompt: apply report structure; generate ToC and executive summary

depth_breadth:
  default_depth: 2                # recursive follow-up rounds
  default_breadth: 3             # parallel sub-queries per round
  max_depth: 4                    # hard cap; depth=4 ~ 81 searches at breadth=3
  max_breadth: 5

output:
  format: markdown                # primary; always produce
  optional: [pdf]                 # generate via ReportLab or LaTeX if requested
  structure:
    - executive_summary
    - table_of_contents
    - findings_sections
    - references                  # numbered, with URL + access date

hallucination_controls:
  closed_world_citations: true    # synthesizer cites only retrieved URLs
  confidence_threshold: 0.6       # refuse-to-answer below this; emit uncertainty statement
  url_liveness_check: true        # post-generation URL verification pass
  cross_source_validation: 2      # require ≥2 independent sources for key claims

delivery:
  default: inline                 # return markdown in agent response
  optional_sinks: [slack, notion, email, webhook]
  scheduling: cron                # for CI agents: daily/weekly recurring runs

cost_guardrails:
  max_web_searches_per_run: 50
  max_fetch_pages_per_run: 20
  estimated_cost_note: >
    At depth=2, breadth=3: ~27 searches + ~15 fetches per run.
    With claude-sonnet-4-6 and web search: estimate $0.50-2.00/report
    depending on report length and source verbosity.
```

### 5.1 Source Diversity Budget (recommended minimums)

| Research Type | Min. Web Searches | Min. Distinct Domains | Internal Sources |
|---|---|---|---|
| Deep research question | 15 | 8 | optional |
| Competitive intelligence | 5 per competitor | 3 per competitor | CRM if available |
| Codebase documentation | 0 (file system only) | N/A | repo files required |
| Market analysis | 20 | 10 | internal docs recommended |
| Literature review | 10 (arXiv/PubMed) | 5 | PDF corpus if available |

### 5.2 Networking Requirements

Researcher agents **require unrestricted outbound networking** for any instance that accesses the open web. This includes:
- All web research and deep research instances
- All competitive intelligence instances
- Literature review agents accessing arXiv, PubMed, Semantic Scholar

The sole exception is **codebase documentation** agents, which operate entirely on the local file system and require **no network access** (or can be sandboxed to internal VCS only).

CI agents additionally need access to:
- Competitor domains (for website monitoring)
- Public APIs: EDGAR, Google Ads Library, LinkedIn (within ToS)
- Proxy/rotation infrastructure if monitoring at scale (to avoid blocking)

---

## 6. Pattern-Specific Questions

When configuring a Researcher agent instance, answer these questions to make the right trade-offs:

**About the question:**
1. Is this a **one-shot** report (single research brief) or **recurring** monitoring (scheduled CI)?
2. Is the question **open-ended** (requires multi-hop exploration) or **bounded** (enumerate specific competitors / documents)?
3. Does the output require **citations for every claim** (regulated / auditable use case) or **summary-level sourcing** (internal briefing)?

**About sources:**
4. Should the agent access **only the open web**, or also **internal documents** (vector store, SQL database, file system)?
5. Are there **domain restrictions** — sources that must be included (EDGAR for SEC filings) or excluded (competitor-owned domains for neutrality)?
6. Does the agent need to **compare against a prior snapshot** (CI delta detection), or is each run independent?

**About output:**
7. What is the **target audience** — technical (can absorb dense citations) or executive (needs summary-first, max 1 page)?
8. What **delivery sink** is expected — inline response, Markdown file, PDF, Slack message, Notion page, dashboard?
9. Is **multi-fidelity output** needed (executive summary + detailed sections + raw appendix)?

**About quality:**
10. What is the **hallucination tolerance**? High-stakes (finance, legal, medical) → use closed-world citations + evidence bundles + URL liveness checks. Internal briefings → confidence threshold + source diversity minimum is sufficient.
11. Is **claim-level auditability** required — can every sentence be traced back to a specific URL and paragraph? If yes, implement W3C PROV-style provenance graph.
12. Should the agent **refuse to answer** when confidence is insufficient, or **always produce output** with uncertainty flagged inline?

**About cost / latency:**
13. What is the **time budget** per report? Interactive (< 60s) → limit depth=1, breadth=3, pre-filter sources. Asynchronous (minutes) → depth=2-4 is practical. Overnight batch → unconstrained depth.
14. What is the **cost budget** per run? Set `max_web_searches_per_run` and `max_fetch_pages_per_run` as hard caps.

**About iteration:**
15. Is a **draft → review → refine** loop needed, or is a single-pass synthesis sufficient? If the audience will review and request revisions, build a Critic agent into the pipeline and expose intermediate artifacts (outline, raw results, draft sections) to the reviewer.
