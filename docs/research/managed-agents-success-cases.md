# Claude Managed Agents: Success Cases & Usage Patterns Research

**Research date:** April 9, 2026  
**Coverage:** 10+ searches across Anthropic docs, customer stories, developer blogs, framework comparisons, and community content

---

## Executive Summary

Claude Managed Agents launched in public beta on **April 8, 2026**. The product is a suite of composable APIs (`/v1/agents`, `/v1/sessions`, `/v1/environments`) that provide a fully managed cloud runtime for long-running AI agents. Early evidence reveals several consistent patterns:

1. **Speed of deployment is the headline metric.** Every customer story cites dramatic reduction in time to production — from months to days or weeks. Anthropic's own tagline is "get to production 10x faster." Sentry's first Managed Agents integration was shipped by a single engineer in weeks. Rakuten deployed specialist agents in five departments within one week per deployment.

2. **The product addresses infrastructure burden, not AI capability.** The value proposition is eliminating custom sandboxing, session management, credential vaults, and agent-loop boilerplate — not the model itself. Developers were already getting value from Claude; Managed Agents removes the scaffolding work.

3. **Three dominant use case clusters have emerged:** (a) automated software engineering workflows (bug fixing, code review, PR automation), (b) cross-department enterprise knowledge work automation (procurement, sales, marketing), and (c) product-level agent embedding (Notion, Asana, Tasklet, Anything).

4. **MCP is the primary integration pattern.** Almost every production case routes tool access through MCP servers rather than custom tool implementations. The combination of MCP + credentials vault + environment templates is the production architecture pattern.

5. **Multi-agent is table-stakes, not a differentiator.** Parallel subagents, agent teams, and orchestrator patterns are assumed. The interesting innovation is how Managed Agents decouples brain (inference) from hands (sandbox/tools), enabling "many brains, many hands" at scale.

6. **Context management is the emerging frontier.** Combining the memory tool with context editing improved agent performance by 39% over baseline on internal Anthropic evaluations. Long-horizon task handling is the core differentiator vs. simple API calls.

7. **Anthropic vs. other frameworks:** Claude Agent SDK is ranked highest for task accuracy (94% in framework comparisons) and reliability. Its key differentiator is native MCP integration and the tightest Anthropic ecosystem fit. Trade-off: single-provider lock-in and fewer pre-built templates than CrewAI or LangGraph.

---

## Key Technical Architecture

From Anthropic's engineering blog ("Scaling Managed Agents: Decoupling the brain from the hands"):

| Concept | Endpoint | What it is |
|---|---|---|
| Agent | `/v1/agents` | Persisted, versioned object: model, system prompt, tools, MCP servers, skills. Created before starting sessions. |
| Session | `/v1/sessions` | A running agent instance inside an environment. References an agent by ID + environment. Produces an event stream. |
| Environment | `/v1/environments` | A container template defining packages, network access, resource configuration. |
| Vault | `/v1/vaults` | Per-user credential container for secrets (GitHub tokens, API keys), isolated per end-user. |
| Skills | (agent-level config) | Anthropic-managed or custom capability packages loaded at agent definition time. |

**Beta header required:** `anthropic-beta: managed-agents-2026-04-01`  
**Pricing:** Standard Claude API token rates + **$0.08 per session-hour** for active runtime  
**Availability:** Direct Anthropic Claude Platform only — not available on AWS Bedrock or Google Vertex AI

**The brain/hands decoupling insight:** Anthropic solved a fundamental engineering challenge by separating the inference layer ("brain") from the execution sandbox ("hands"). This means:
- Sessions can start before containers are provisioned (reduced time-to-first-token)
- Many sessions can share sandboxes (cost efficiency)
- Brain and hands can be in different locations (VPC support without peering)
- Brains can pass hands to one another (multi-agent handoff)

---

## Detailed Findings by Use Case Category

### 1. Automated Bug Fixing & Code Quality

#### Sentry — End-to-end bug detection to PR (Managed Agents)
- **Source:** https://www.anthropic.com/customers/sentry
- **What they built:** Extended their existing Seer AI debugging agent to go from root cause analysis to merge-ready pull requests using Claude Managed Agents.
- **Features used:** Managed Agents (sessions, environments), Claude Managed infrastructure for secure sandboxing, sessions event streaming
- **Results:**
  - Over 1 million root cause analyses per year
  - 600k+ pull requests reviewed per month
  - Initial Managed Agents integration shipped in **weeks by a single engineer**
- **Workflow:** Seer detects issue → queries source code and telemetry for root cause → hands off to Claude agent on Managed Agents → agent plans solution, implements fix, runs tests, creates PR
- **Key insight:** "Without Managed Agents, Sentry would have needed to build their own sandboxing capabilities and agent runtime from scratch." — Indragie Karunaratne, Senior Director of Engineering AI/ML, Sentry
- **What worked:** Managed Agents let the team focus on expanding Seer's domain logic rather than building and maintaining agent infrastructure

#### Community: ralph-sentry-fixer (Open Source)
- **Source:** https://github.com/friebetill/ralph-sentry-fixer
- **Who:** Independent developer (friebetill)
- **What they built:** Three-phase agentic loop (Plan → Build → Review) connecting to Sentry via MCP, analyzing bugs, and creating PRs with Claude Code
- **Results:** 132 bugs fixed in a Flutter app, all PRs merged, zero regressions
- **Features used:** MCP (Sentry), Extended Thinking for consequence analysis, GitHub CLI
- **Workflow:** Load issues from Sentry → prioritize by events × users → analyze code → implement fix → run `flutter analyze` → create PR → process review comments

#### Werun.dev — Production Engineering Workflows
- **Source:** https://werun.dev/blog/claude-code-in-production-real-world-ai-assisted-engineering-workflows
- **What they built:** B2B web development agency integrating Claude Code into production pipelines for WordPress, Webflow, and Shopify environments
- **Features used:** Claude Code, n8n integration for monitoring, custom agentic pipelines
- **Outcomes:** Automated data migrations, performance optimization (consistent 90+ Core Web Vitals), autonomous dependency management for hundreds of client sites
- **Pattern:** Error log monitoring → n8n webhook → Claude agent → diagnose and PR fix → Slack notification

### 2. Large-Scale Code Migrations

#### Spotify — Fleet-wide code migrations (Claude Agent SDK)
- **Source:** https://www.anthropic.com/customers/spotify
- **What they built:** Background coding agent integrated into their Fleet Management infrastructure, handling complex code migrations at scale
- **Features used:** Claude Agent SDK (renamed from Claude Code SDK), built on Claude Code, automated pipeline from natural language prompt to merged PR
- **Results:**
  - Up to **90% time savings** on complex code migrations
  - **650+ pull requests merged per month** from agent
  - Handles migrations previously "too complex to script" (Java AutoValue to Records, framework upgrades with breaking changes, codebase-wide context propagation enforcement)
- **Workflow:** Engineer describes migration in natural language → agent navigates codebase → implements change → runs formatting, linting, builds, tests → verification → submits PR
- **Key insight:** Platform teams now take on projects previously "too costly and complex" — e.g., enforcing explicit context propagation for all Java gRPC services

#### Rakuten — Enterprise-wide development acceleration (Claude Managed Agents)
- **Source:** https://www.anthropic.com/customers/rakuten
- **What they built:** Enterprise agents across product, sales, marketing, finance, and HR that plug into Slack and Teams
- **Features used:** Claude Managed Agents, Claude Code, Slack/Teams integration
- **Results:**
  - 79% reduction in time to market (24 days → 5 days)
  - 7 hours of sustained autonomous coding on complex open-source refactoring
  - 99.9% accuracy on complex code modifications
  - 97% reduction in critical errors
  - Each specialist agent deployed **within one week**
- **Pattern:** Employees assign tasks via Slack/Teams → Managed Agents run in sandboxed environments → deliverables (spreadsheets, slides, apps) returned to the employee

### 3. Software Development Platform Embedding

#### Anything — No-code app building for 1.5 million users (Claude Agent SDK)
- **Source:** https://www.anthropic.com/customers/anything
- **What they built:** Full-stack app building agent for non-technical users, handling databases, backend logic, mobile deployment, App Store submission, and payments
- **Features used:** Claude Agent SDK, Claude Opus 4.6, subagents for specialized tasks
- **Results:**
  - **800,000+ apps built** in five months
  - **91-96% agent success rate**
  - Integration completed in **one day** using Agent SDK
  - Use cases range from simple tools to full-stack apps with payments, AI integrations, and App Store presence
- **Notable users:** Non-technical founder built a full recruiting ATS; a film director launched a streaming app; a musician built a marketplace with ElevenLabs API
- **Key insight:** Claude Opus 4.6 performed well enough from the start that they skipped the weeks of testing typically required for new model evaluation

#### Tasklet — General-purpose business automation (Claude Platform)
- **Source:** https://www.anthropic.com/customers/tasklet
- **What they built:** Business automation platform where users describe tasks in natural language and agents execute them 24/7, built on long-lived Claude conversations
- **Features used:** Long-running Claude sessions, MCP integrations (3,000+ pre-built), browser use, computer use, Instant Apps (live interactive web apps generated on-the-fly)
- **Results:**
  - **160% month-over-month revenue growth** reaching $2.5M ARR in five months
  - **450,000 agent actions per day** across all customer agents
  - **2,000 new agents created daily** by users
  - Intelligent email triage, revenue reconciliation (Stripe + Ramp), deal desk pipelines, competitor monitoring
  - One customer built an entire multi-agent VC firm back-office in under a week
- **Architecture:** Three core capabilities per agent — Connections (tool access), Memory (persistent state), Compute (execution)

### 4. Enterprise Operations & Procurement Automation

#### Duvo — Enterprise procurement and supply chain (Claude Agent SDK)
- **Source:** https://www.anthropic.com/customers/duvo
- **What they built:** AI agents running procurement, supply chain, and category management for multi-billion-euro retail and CPG companies, operating through actual system UIs (ERPs, supplier portals, spreadsheets, email, phone calls)
- **Features used:** Claude Agent SDK, MCP, computer use (operating actual system interfaces), Zero Data Retention mode on every API call
- **Results:**
  - **€2.8M+ in annualized savings** within three months for one retailer (Rohlik Group)
  - **40%+ team capacity freed** on average across enterprise operations
  - **Eight weeks** from first conversation to production deployment with measured savings
  - Production deployment within **days** of adopting the Claude Agent SDK
- **Workflow example:** Agent logs into supplier portal → extracts delivery status for 50 purchase orders → cross-references with ERP data → flags discrepancies → drafts resolution actions → surfaces to team for decision
- **Key insight from Paris (Duvo):** "Other providers offer a model. Anthropic offers the infrastructure to run agents in production with the governance enterprises require."
- **Why single-provider:** MCP + Agent SDK + computer use provided a complete foundation, and Zero Data Retention on every call met enterprise security requirements

### 5. Workspace & Knowledge Work Automation

#### Notion — Custom Agents for teams (Claude Managed Agents)
- **Source:** https://www.anthropic.com/customers/notion, https://www.notion.com/blog/introducing-custom-agents, LinkedIn post April 8, 2026
- **What they built:** Custom Agents feature (launched Feb 24, 2026) backed by Claude Managed Agents, allowing users to create autonomous AI teammates that run 24/7 against Notion workspace, Slack, Mail, Calendar, and MCP-connected tools
- **Features used:** Claude Managed Agents (cloud-hosted sessions), MCP connectors for Slack/Figma/Linear/HubSpot, trigger-based automation, agent teams
- **Results:**
  - **21,000+ custom agents** built by early testers
  - **2,800 agents running around the clock** at Notion internally
  - 30 tasks handled in parallel by one user demonstrating the system
  - Companies like Ramp, Remote, Braintrust, and Clay active early adopters
  - Remote replaced their entire IT help desk with a single agent, saving **20 hours per week**
  - Ramp's team deployed 300+ agents, including a "Product Oracle" answering dozens of daily questions
- **Workflow:** User creates agent with natural language description → sets triggers (database events, Slack mentions, schedules) → agent reads from Notion/Slack/connected tools → performs tasks → logs all runs for audit
- **Key insight from Eric Liu (PM at Notion):** "Having a harness that can do long running tasks is really essential... The managed agent product is like a playground for us on the development side."

#### Zapier — Internal AI culture and customer-facing agents
- **Source:** https://www.anthropic.com/customers/zapier, https://www.anthropic.com/customers/zapier-cowork-qa
- **What they built:** Company-wide AI adoption using Claude Enterprise/Cowork, plus Claude integration in their automation platform for customers
- **Features used:** Claude Enterprise, Claude Cowork, MCP platform strategy for customer-facing agents, Zapier MCP (9,000+ app integrations)
- **Results:**
  - **89% AI adoption** across all employees (highest in company history)
  - **800+ AI agents deployed** internally (exceeding employee count)
  - **10x year-over-year** growth in Anthropic app usage
  - Marketing team: ~15 minutes from new positioning concept to shareable homepage draft
  - Engineering: 15 SQL queries synthesizing live data from 6 engineering systems in one Cowork session
- **Pattern:** Cowork treated as "a team member with a terminal", not a conversation tool

#### Jamf — Structured workflow tools (Claude Cowork)
- **Source:** https://www.anthropic.com/customers/jamf
- **What they built:** Replaced spreadsheets and checklists with guided, reusable conversational workflows using Claude Cowork
- **Features used:** Claude Cowork, Claude Enterprise (16 departments), Jira integration, custom skills
- **Results:**
  - 45 minutes to build a conversational UI with branching logic, role-based filtering, Jira integration, progress tracking, and structured file export
  - Previously equivalent build: full team and three months
  - Rolled out across all 16 departments

#### Asana — AI Teammates for work management
- **Source:** https://www.anthropic.com/customers/asana, https://www.anthropic.com/customers/asana-qa
- **What they built:** AI Teammates powered by Claude Opus 4.6, embedded in Asana's Work Graph data model
- **Features used:** Multi-agent architecture, Claude Opus 4.6 for high-judgment work, different models for different subtasks
- **Results:** 150,000+ enterprise customers; increased goal clarity and project velocity
- **Key insight from Arnab Bose (CPO, Asana):** AI Teammates are "multiplayer by design" — designed for teams rather than individual productivity, with access to full Work Graph context

### 6. Financial Services Automation

#### NBIM (Norges Bank Investment Management)
- **Source:** https://www.claude.com/blog/building-ai-agents-in-financial-services
- **What they built:** AI agents for analytical and operational tasks across the investment management workflow
- **Results:** Employees save **hundreds of cumulative hours per week**
- **Features used:** Claude via AWS Bedrock, agentic analytical workflows

#### Brex
- **Source:** https://www.claude.com/blog/building-ai-agents-in-financial-services
- **What they built:** AI anomaly detection agent reviewing 100% of transactions, grouping related expenses, and providing aircover for financial professionals
- **Features used:** Claude via AWS Bedrock, transaction analysis

#### Intuit TurboTax
- **Source:** https://www.claude.com/blog/building-ai-agents-in-financial-services
- **What they built:** AI financial assistant generating clear tax explanations for millions of customers; so successful the AI-powered feature became one of the company's top-rated features

### 7. Developer Tools & Code Review Automation

#### Anthropic Internal — Multi-agent code review
- **Source:** https://www.claude.com/blog/code-review
- **What they built:** Code Review product that dispatches a team of agents on every PR
- **Features used:** Multi-agent teams (agents search in parallel, verify bugs, rank by severity), Claude Code
- **Results:**
  - PRs with substantive review comments went from **16% to 54%**
  - On large PRs (1,000+ lines), **84% get findings**
  - Average cost: **$15-25 per review**, scaling with PR size
- **Workflow:** PR opened → team of agents dispatched → agents search for bugs in parallel → verify bugs (filter false positives) → rank by severity → single high-signal overview posted to PR

#### Developer community: GitHub Actions PR review bots
- **Multiple sources:** Medium posts, DEV community, personal blogs
- **Common pattern:** `anthropics/claude-code-action@v1` in GitHub Actions YAML, triggered on `pull_request` events, Claude reviews diff, posts structured comments
- **Cost:** Typically $0.02-0.10 per PR review using Claude Sonnet
- **Example developer result:** 2-3 hours/day on code review → 30-45 minutes (mostly architecture-level), freeing ~10 hours/week

#### ServiceNow — Enterprise app development & productivity
- **Source:** https://www.anthropic.com/news/servicenow-anthropic-claude
- **What they built:** Claude as default model for ServiceNow Build Agent (enterprise coding solution), plus Claude Code for 29,000+ employees
- **Results:**
  - Build Agent usage expected to quadruple in 12 months
  - Targeting **50% reduction** in time-to-implement for product deployment
  - Agentic applications in healthcare: research analysis, claims authorization

### 8. Data Analysis & Research

#### Zapier Engineering (Cowork)
- **Source:** https://www.anthropic.com/customers/zapier-cowork-qa
- **What they built:** Engineering analysis workflows connecting Cowork to their entire tech stack
- **Features used:** Cowork (agentic workspace), Claude with SQL access to multiple systems
- **Results:** 15 SQL queries synthesizing live data from 6 systems (GitLab, Jira, Productboard, OpsLevel, etc.) in one session, producing an interactive dashboard with quantified inefficiency breakdown by team

---

## Common Integration Patterns

### Pattern 1: MCP Toolset Architecture (Most Common)
The dominant production pattern uses MCP servers rather than custom tool implementations:
```
Agent (system prompt + skills)
  → MCP Server (e.g., GitHub, Sentry, Linear)
    → Credentials Vault (per-user tokens, isolated)
      → Environment (container template)
        → Session (specific task run)
```
- Credentials vault isolates per-user tokens (no shared tokens in agent definition)
- MCP servers handle OAuth, making it safe to build multi-tenant agents
- Used by: Sentry, Notion, Tasklet, Duvo

### Pattern 2: Issue-to-PR Automation Loop
The most common end-to-end workflow in the developer tooling space:
```
Error Monitor (Sentry/logs) 
  → Webhook trigger
    → Agent session starts
      → Clone repo + analyze context
        → Implement fix
          → Run tests/lint
            → Create PR
              → Notify engineer
```
- Used by: Sentry (Managed Agents), Werun.dev (n8n), Open Source (ralph-sentry-fixer)
- Key insight: This loop is now a commodity pattern, not a novel architecture

### Pattern 3: Enterprise Department Agent Deployment
The Rakuten/Notion/Zapier pattern for internal enterprise agents:
```
Slack/Teams trigger (task assigned to agent)
  → Agent picks up task with workspace context (docs, PRDs, data)
    → Long-running session in managed cloud environment
      → Deliverable produced (spreadsheet, slide deck, app, analysis)
        → Human review → approve/request changes
          → Output delivered back to workflow
```
- Key differentiator: Agents have access to full organizational context, not just task description
- Human-in-loop is designed at the review/approval step, not every tool call

### Pattern 4: Background CI/CD Agent
For automated pipeline integration:
```
PR opened (GitHub webhook)
  → CI/CD runs Claude agent via SDK/Action
    → Agent reads codebase context
      → Performs review/fix/migration
        → Commits result or posts structured feedback
          → Metrics tracked (cost per PR, acceptance rate)
```
- Used by: Spotify (migrations), Anthropic Code Review product, hundreds of teams via `claude-code-action`

### Pattern 5: Multi-Agent Orchestration
For complex tasks exceeding single context window:
```
Orchestrator Agent
  ├── Research subagent (web search, data retrieval)
  ├── Analysis subagent (insight extraction)  
  ├── Writer subagent (report generation)
  └── Review subagent (quality gate)
```
- Native in Claude Code via Agent Teams (experimental, requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- Available via Agent SDK via `agents` option with handoff patterns
- Used by: Anthropic Code Review, Asana AI Teammates, Anything (app building subroutines)

### Pattern 6: Credential Vault for Multi-Tenant SaaS
For products serving multiple end users:
```
Per-user vault created at signup
  → User credentials stored (GitHub token, API keys)
    → Sessions reference vault by ID
      → Agent uses credentials for that user's resources only
        → Credentials never shared across users
```
- Used by: Any SaaS embedding Managed Agents for their customers
- Anthropic proxies MCP calls server-side using vault credentials — no round-trip required

---

## Feature Usage Analysis

### Most Used Features (by appearance in case studies)
1. **Sessions** — Universal, every Managed Agents deployment
2. **MCP integration** — Used in nearly every production case
3. **Skills** — Used by Notion, Rakuten, Tasklet; common in Claude Code context
4. **Multi-agent / subagents** — Used in Sentry, Anthropic internal, Asana, Anything
5. **Environments** — Used to configure container templates, mentioned in Managed Agents deployments
6. **Credential Vaults** — Used in production multi-tenant setups (Sentry, Notion-style deployments)
7. **Resources (GitHub repo mounts)** — Used in coding agent workflows

### Features in Research/Experimental Preview
- **Multi-agent coordination** — Research preview as of April 2026
- **Context management (memory tool + context editing)** — Public beta; 39% performance improvement on internal eval
- **Agent Teams** — Experimental, disabled by default in Claude Code

---

## Competitor Comparison Summary

| Framework | Best For | Claude Agent SDK Advantage |
|---|---|---|
| LangGraph | Complex stateful workflows, Python-first teams | Claude SDK: simpler setup, native MCP, no graph complexity |
| CrewAI | Role-based multi-agent teams, Fortune 500 adoption | Claude SDK: higher accuracy (94% vs CrewAI's ~89%), native tooling |
| AutoGen (Microsoft) | Enterprise in Microsoft ecosystem, conversational multi-agent | Claude SDK: better performance outside Azure, cleaner MCP |
| OpenAI Agents SDK | ChatGPT ecosystem teams | Claude SDK: consistently ranked higher task completion accuracy |
| LangChain | Broad ecosystem, RAG pipelines | Claude SDK: less boilerplate, better out-of-box reliability |

**Claude Agent SDK Rankings (from third-party framework comparisons):**
- TechPick AI: Ranked #1 overall (9.1/10) for production reliability, 94% task completion accuracy
- Developers Digest: Recommended specifically when "building with Claude and need MCP integration"
- Key weakness identified: No built-in visual workflow editor; smaller pre-built template ecosystem vs. CrewAI

**Why teams choose Claude over other frameworks:**
1. Highest task completion accuracy in real-world testing
2. Native MCP integration (other frameworks require third-party adapters)
3. Extended thinking / long-horizon reasoning for complex tasks
4. Single-provider governance model (Zero Data Retention, compliance-grade audit)
5. Continuous improvement: every model upgrade benefits the product without agent rewrites

---

## Notable Quotes

> "With Managed Agents, our power users become like Galileo, contributing across domains far beyond a single specialty or discipline. We deploy each specialist agent within a week, managing long-running tasks across engineering, product, sales, marketing, and finance."
> — Kaji, Rakuten

> "Turns out telling developers what's wrong with their code isn't enough: they want you to fix it too."
> — Indragie Karunaratne, Senior Director of Engineering AI/ML, Sentry

> "Other providers offer a model. Anthropic offers the infrastructure to run agents in production with the governance enterprises require."
> — Paris, Founder, Duvo

> "Claude has consistently delivered the strongest performance for large-scale code transformation work, which is why it remains our default choice."
> — Spotify engineering team

> "The biggest mistake people make is treating Cowork as a conversation that you're participating in. You need to hand off work to Claude, then step away."
> — Zapier team member

> "2025 was the year of coding agents. We think 2026 will be the year of general purpose knowledge work agents."
> — Lee, Founder, Tasklet

> "The human is still making the decisions. Cowork just makes sure the process doesn't stall or come back with the wrong output."
> — Nick Benyo, Software Engineer, Jamf

> "Our engineers are now able to execute fleet-wide migrations at a pace that simply wasn't possible before."
> — Max (Spotify engineering team)

> "Building Managed Agents meant solving an old problem in computing: how to design a system for 'programs as yet unthought of.'"
> — Anthropic Engineering Blog (Lance Martin, Gabe Cemaj, Michael Cohen)

---

## Implications for Pre-Built Skill Templates

Based on these patterns, the highest-value orchestrator skill templates would be:

### High Priority (Validated by Multiple Customers)
1. **Issue-to-PR Loop** — Sentry webhook → analyze → fix → PR (Sentry, werun.dev, ralph-sentry-fixer, Zapier pattern)
2. **Code Review Agent** — PR opened → multi-agent review → structured feedback (Anthropic internal, Spotify, community)
3. **Department Knowledge Worker** — Task assigned via Slack → context-aware execution → deliverable (Rakuten, Notion, Zapier)
4. **Fleet-Wide Migration** — Natural language migration description → codebase-wide implementation → PRs (Spotify)
5. **Procurement/Operations Automation** — Legacy system interaction → data extraction → reconciliation → action (Duvo)

### Medium Priority (Single Large Customer or Pattern)
6. **Financial Transaction Monitoring** — Review all transactions → anomaly detection → alerts (Brex pattern)
7. **Documentation Generation** — Analyze codebase → generate API docs/READMEs → commit (multiple dev patterns)
8. **Research Synthesis** — Multi-source retrieval → analysis → structured report (financial services, NBIM)
9. **Support Ticket Triage** — Incoming ticket → classify → retrieve context → draft response (HappyFox, Notion agents)
10. **Competitor Monitoring** — Scheduled trigger → multi-source research → digest report (Tasklet use case)

### Emerging / Future (Research Preview Features)
11. **Multi-Agent Code Review Team** — Parallel specialist reviewers (security, performance, coverage) → unified report
12. **Ambient Agent** — Complex project broken into parallel subagents, reassembled (Rakuten roadmap item)
13. **Self-Improving Agent Loop** — Agent identifies its own workflow gaps and proposes skill improvements (Anything roadmap)

---

## Sources

| Source | URL | Type |
|---|---|---|
| Anthropic Engineering Blog | https://www.anthropic.com/engineering/managed-agents | Official |
| Managed Agents Launch Blog | https://claude.com/blog/claude-managed-agents | Official |
| Managed Agents Quickstart | https://platform.claude.com/docs/en/managed-agents/quickstart | Official |
| API Overview | https://docs.anthropic.com/en/api/getting-started | Official |
| Sessions API Reference | https://platform.claude.com/docs/en/api/beta/sessions | Official |
| Sentry Customer Story | https://www.anthropic.com/customers/sentry | Official |
| Rakuten Customer Story | https://www.anthropic.com/customers/rakuten | Official |
| Spotify Customer Story | https://www.anthropic.com/customers/spotify | Official |
| Duvo Customer Story | https://www.anthropic.com/customers/duvo | Official |
| Anything Customer Story | https://www.anthropic.com/customers/anything | Official |
| Tasklet Customer Story | https://www.anthropic.com/customers/tasklet | Official |
| Notion Custom Agents Blog | https://www.notion.com/blog/introducing-custom-agents | Official |
| Zapier Customer Story | https://www.anthropic.com/customers/zapier | Official |
| Jamf Customer Story | https://www.anthropic.com/customers/jamf | Official |
| Asana Customer Story | https://www.anthropic.com/customers/asana | Official |
| Financial Services Guide | https://www.claude.com/blog/building-ai-agents-in-financial-services | Official |
| ServiceNow Partnership | https://www.anthropic.com/news/servicenow-anthropic-claude | Official |
| WIRED Launch Coverage | https://www.wired.com/story/anthropic-launches-claude-managed-agents/ | Press |
| Build Fast with AI Review | https://www.buildfastwithai.com/blogs/claude-managed-agents-review-2026 | Community |
| O-mega.ai Guide | https://o-mega.ai/articles/claude-managed-agents-the-2026-guide | Community |
| YouTube: Mansel Scheffel | https://www.youtube.com/watch?v=3Orvel4oG1g | Community |
| YouTube: Rob The AI Guy | https://www.youtube.com/watch?v=A4xEzJ9Dxec | Community |
| ralph-sentry-fixer GitHub | https://github.com/friebetill/ralph-sentry-fixer | Community |
| Sentry for AI GitHub | https://github.com/getsentry/sentry-for-claude | Community |
| ZenML Production Agents | https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments | Community |
| Framework Comparison | https://developersdigest.tech/blog/ai-agent-frameworks-compared | Community |
| TechPick AI Framework Test | https://techpickai.com/en/ai-tools/best-ai-agents/ | Community |
| Production Cookbook | https://platform.claude.com/cookbook/managed-agents-cma-operate-in-production | Official |
| Claude Code Review Blog | https://www.claude.com/blog/code-review | Official |
| Context Management Blog | https://www.anthropic.com/news/context-management | Official |
| Werun.dev Blog | https://werun.dev/blog/claude-code-in-production-real-world-ai-assisted-engineering-workflows | Community |
| Claude Directory Guide | https://www.claudedirectory.org/blog/claude-code-agents-guide | Community |
| ClaudeRun Architecture | https://clauderun.com/ | Community |
| alirezarezvani/claude-skills | https://github.com/alirezarezvani/claude-skills | Community |
| Zapier Agentic Survey 2026 | https://zapier.com/blog/ai-agents-survey/ | Market Research |
