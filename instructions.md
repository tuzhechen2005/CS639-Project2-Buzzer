# Project 2: Buzzer — Instructions

## Overview

This is a team-based project (2–4 students). Your team will use AI tools to understand, modify, and extend **Buzzer**, an existing real-time quiz platform, practicing professional software development workflows: version control, CI/CD pipelines, and AI-assisted development.

Over the project you will restructure the host and admin interfaces, add two new question types, add image support, give the UI a proper visual design with light and dark themes, and cover it all with integration tests — while following a design-before-code AI methodology throughout.

How your work is graded is defined in [rubric.md](rubric.md). Read it alongside this document: the tasks below say *what to do*; the rubric says *how it's assessed*.

## Getting Started

1. Follow the **First-time setup** section of [README.md](README.md) — environment, JWT keys, Docker stack, migrations, frontend dev servers.
2. Read [docs/realtime.md](docs/realtime.md) before touching anything in the game loop — it traces how an answer flows through the Socket.io gateway and explains the tooling for simulating players.
3. Load the demo quiz (`python scripts/seed_demo.py`) and play a round with simulated players (`python scripts/simulate_players.py --room <CODE>`) so you've seen the system work end to end before changing it.

## Required Reading

> **["Elephants, Goldfish and the New Golden Age of Software Engineering"](https://drensin.medium.com/elephants-goldfish-and-the-new-golden-age-of-software-engineering-c33641a48874)** — *Dave Rensin*
>
> The most dangerous mistake developers make with AI is skipping design and going straight to code. This article introduces two complementary AI session strategies — the **Elephant** (a long-running session that accumulates deep context) and the **Goldfish** (a fresh session with no memory, used to stress-test your design) — and argues that writing a detailed design document *before* touching any code is now the most important skill in software engineering. Task T3 requires you to follow this workflow.

## Tasks

### T0 — Verify AI Session Logging

Before starting any development work, every team member must verify that Claude Code session logging is working in this repository:

1. Open a Claude Code session in the project directory.
2. Have a brief interaction (e.g., ask it to explain a file or how a system works).
3. Confirm a new log file was created and committed in `ai_log/` — the logging hook does this automatically.
4. Push your branch and confirm the log file appears on the remote.

Complete this before any other task. Your AI usage throughout the project is part of your grade, and unlogged sessions cannot be credited.

### T1 — Team Git Workflow

**Goal:** all work is tracked in Git using professional team practice, for the entire project.

| Requirement | Description |
|----------|-------------|
| Identity | Every member commits under one consistent identity: set `git config user.email <your-netid>@wisc.edu` in this repository before your first commit. Work is attributed to you by commit email — commits under stray personal emails may not be credited. |
| Branching | Each independent feature or fix lives on its own branch. Branch names are descriptive (e.g., `feature/host-roster-edit`, `fix/admin-game-access`). |
| Commits | Commits are atomic (one logical change per commit) with clear, descriptive messages in a consistent format (e.g., imperative mood: "Add roster upload to host interface"). |
| Merges | Branches are merged back to `main` via merge requests — never direct pushes. |
| No force pushes | History on `main` is never rewritten. |

*Suggestion*: Use one branch and one MR per T-numbered task by default for each group member, not one per implementation slice. Split further only if the task naturally contains independent, separately-reviewable deliverables (e.g., different members each own a clearly separate piece of a T* task). A bug found along the way, unrelated to the current task, always gets its own branch and MR.

### T2 — Keep the CI Pipeline Green

**Goal:** every merge request passes the existing CI/CD pipeline before merging. Do not bypass or modify the pipeline to make it pass artificially.

The pipeline (defined in `.gitlab-ci.yml`) runs on every merge request:

| Check | Command | Requirement |
|-------|---------|-------------|
| Python style | `ruff check backend/ scripts/` and `ruff format --check backend/ scripts/` | No style or lint errors. Run `ruff format backend/ scripts/` locally to auto-fix before pushing. |
| Frontend types | `tsc --noEmit` (all three apps) | No TypeScript type errors. |
| Secret detection | GitLab built-in scan | No secrets or credentials committed. |

**Merge request approval:** every MR must be reviewed and approved by a teammate who did **not** author the code. Authors may not approve their own MR.

### T3 — Build Context and Design Before You Code (Elephant/Goldfish)

**Goal:** follow the Elephant/Goldfish workflow from the required reading for the UI restructuring task (T4) and all the following tasks. This is not optional — the design artifacts are deliverables.

**How you run this process is up to you.** The six steps below describe it as a manual, prose-driven workflow. This repo also ships a working Claude Code implementation of the same process — skills (`context-hierarchy`, `design-discussion`, `write-spec`, `goldfish-test`, `mean-review`) and rules (`no-code-during-design`, `sycophant-challenge`) under `.claude/`, documented in [CLAUDE.md](CLAUDE.md). Using them is **encouraged, not required** — following the steps below by hand earns identical credit. Extending or replacing them with your own skills/rules is also fair game (see "Going further" below); the grading criteria in [rubric.md](rubric.md) look for the process and its artifacts, not which mechanism produced them.

**Step 1 — Build codebase context bottom-up (the README trick).**
Divide the source directories among your team and have each member generate a `README.md` for their assigned leaf directories using AI — or, if you're using the provided tooling, run the `context-hierarchy` skill to build the same context as nested `CLAUDE.md` files instead. Either artifact is graded the same way; pick whichever you'd rather maintain. Work bottom-up: start at the deepest directories, have AI write a summary of what the code in that directory does, verify it yourself (5–10 minutes per directory), then roll up to the parent directory and repeat, up to the project root's source folders.

Directories to cover (divide among team members):
- `backend/app/routers/`, `backend/app/services/`, `backend/app/websocket/`, `backend/app/models/`, `backend/app/schemas/`, `backend/app/common/`
- `frontend/host/src/pages/`, `frontend/host/src/components/`, `frontend/host/src/lib/`
- `frontend/player/src/pages/`, `frontend/player/src/components/`, `frontend/player/src/lib/`
- `frontend/admin/src/pages/`, `frontend/admin/src/components/`, `frontend/admin/src/lib/`

These become lightweight context you can hand to any future AI session. Commit them to the repository.

**Step 2 — Load context with the Elephant.**
Start a Claude Code session (your Elephant) and use it to deeply explore the codebase — aided by the context files you just created. Ask how the admin and host interfaces work, how role-based access is enforced, how the frontend routes are structured, and where the relevant backend endpoints live. Push back, ask follow-up questions, and don't accept surface-level answers.

**Step 3 — Design, don't implement.**
Still in the same Elephant session, hold a 20–30 minute back-and-forth design conversation about the T4 restructuring. Ask the AI to challenge your assumptions, identify risks, and propose alternatives. Request a technical plan in prose and pseudocode — **not code**. Keep asking "what could go wrong?" and "what are we missing?" (The provided `design-discussion` skill and `sycophant-challenge` rule automate this step and the pushback, if you're using the tooling.)

**Step 4 — Write a design document.**
Produce `docs/design-<feature>.md` — or, using the provided `write-spec` skill, `docs/plans/<feature-slug>.md` — capturing: the problem being solved; the technical plan including every file that will be touched; alternatives considered and why they were rejected; step-by-step implementation details. Either location is graded the same way. This document must be committed *before* any implementation code.

**Step 5 — Run the Goldfish test.**
Open a **brand new** AI session (no prior context) — or invoke the provided `goldfish-test` skill in one. Give it only the design document. Ask it to explain what it learned, identify gaps or ambiguities, and critique the plan. Revise the design document based on what the Goldfish reveals. A design document that only makes sense in the context of your Elephant conversation is not ready.

**Step 6 — Implement against the document.**
Hand the finalized design document to AI with explicit instructions to follow it. Treat the document as the authoritative specification. If implementation reveals a flaw in the design, update the document first, then the code. Consider closing with the provided `mean-review` skill — an adversarial pass looking for what the spec implied but the code didn't do.

**Going further.** The provided skills and rules are a starting point, not a ceiling — if your team develops a workflow worth codifying (a review checklist, a scaffolding pattern for new question types, anything you find yourselves repeating), writing it as your own skill or rule under `.claude/` is genuinely good AI practice and counts in your favor: it's exactly the kind of deliberate, thoughtful AI usage the grading notes reward, and gives you something concrete to describe in your individual markdown document (T10) and at the TA code review (T11).

### T4 — UI Restructuring (Host and Admin Interfaces)

**Goal:** the admin interface currently handles both admin-level tasks and tasks a Host should own. Restructure both interfaces.

**Host interface — add the following capabilities:**

| Capability | Description |
|------------|-------------|
| Download session summary | The host can download an HTML file summarizing the questions and results for a completed session. |
| Download session scores | The host can download a CSV of per-player scores for a completed session. |
| Roster management | The host can view and update the roster for any course they have been granted HOST access to (add/deactivate entries via CSV upload). |
| Game management | The host can create new games and add, edit, delete, and reorder questions and their scoring. |
| Course-specific games | Games are attached to a specific course at creation time. A game is only accessible to hosts and players of that course. |

**Admin interface — restructure as follows:**

| Requirement | Description |
|-------------|-------------|
| Admin-first layout | The UI prioritizes admin-specific tasks: user account management, course creation, granting course/game access. |
| Full access retained | Admins can still perform all host and player actions, but these are secondary in the navigation/layout. |

Your changes must integrate with the existing role and permission system — no bypassing access checks.

**Deliverables:** the committed context-hierarchy files and design doc from T3; the restructured interfaces; integration tests (T5).

### T5 — Integration Testing

**Goal:** the new capabilities from T4, T7, and T8 are covered by integration tests that run against the live Docker stack, using the existing pytest framework in `tests/integration/`.

- Tests verify behavior, not just that endpoints respond.
- Cover both success paths and relevant error/access-control cases.
- Existing tests must not be deleted or weakened.
- If tests start hitting resource limits that seem unrelated to your changes, check whether every deletion path cleans up what its matching creation path set up, in both datastores.

### T6 — Quiz/Game JSON Files

**Goal:** each team member creates **two quiz game JSON files** and imports them into the running application.

*Note that*, T6 cannot be fully completed until T7 is done. 
This is normal since the real development is iterative:
you start T6 with games using the existing question types;
after T6, you might come up with a new idea like T7; 
then you need to go back to T6 again.

| Requirement | Description |
|-------------|-------------|
| Quantity | 2 games per team member |
| Question types | Each game includes at least one question of every supported type: `multiple_choice`, `true_false`, `fill_in_the_blank`, `multi_select` |
| Grading modes | Each game includes questions using both `ACCURACY` and `COMPLETENESS` |
| Classroom game | One game per member suitable for class use (educational content, professional tone) |
| Party game | One game per member suitable for a social gathering (fun, broadly accessible) |
| New question types | At least one game per member includes questions using each of the team's new question types (T7) |
| Format | Files conform to the game JSON schema (see README) and import cleanly via the Admin UI or API |
| Format version | Files ship as `"version": 1`. If your image work (T8) extends the format, you may bump the version — but importing unmodified version-1 files must keep working, and your game files must import cleanly into your own application either way |
| Committed | All files committed under `sample_games/` |

**Note that**, the demo games already in `sample_games/` (used by `seed_demo.py`) are starter content and don't count toward the requirement of committing new, distinctly-named files.

### T7 — New Question Types

**Goal:** design and implement **two new question types** from scratch. The codebase ships with `multiple_choice`, `true_false`, `fill_in_the_blank`, and `multi_select`; your team adds two more.

**Constraints:**

| Constraint | Description |
|------------|-------------|
| Canvas-based | One of the two types uses an HTML Canvas as the player's interaction surface (e.g., drawing, clicking a region, placing an object). |
| Context | One type suits a classroom setting; the other suits a group party. Which maps to which is your team's choice. |
| Grading | Each type has a defined scoring approach. How scoring works is your team's design decision. |

**Designing for a subject.** The strongest question types don't start from "what can we build" — they start from "what would this look like if a teacher of this subject designed it." Pick a subject area (math, chemistry, geography, music, literature, coding — anything) and ask: what's the most natural way an expert in that field would actually want to quiz someone, in the time it takes to answer one question? That question usually points straight at a good interaction design, and often at your canvas type.

A few real examples to prime your thinking — not to copy, but to see the pattern. Each of these scores one answer at a time, immediately, the same shape as a single Buzzer question:

- **[MapTap](https://maptap.gg/)** (geography) — shown a place tied to a real historical event, you find it on a 3D globe with one tap; the game's "Gauntlet" mode is literally a timed run through a set of locations, one shot each. The interaction *is* the geography: you're not naming a country, you're pointing at where it is. A "click the location on a map/image" canvas question type is a direct translation of this into Buzzer.
- **[Guess the Correlation](https://www.guessthecorrelation.com/)** (math/stats) — shown a scatter plot, you submit one numeric guess (0–1) for the correlation coefficient and get scored immediately on how close you were — full credit within 0.05, partial within 0.10, nothing beyond that. It's a clean model for a question type built around a single continuous-valued guess with distance-based partial credit, instead of binary right-or-wrong.
- **[GuessElement](https://guesselement.com/)** (chemistry) — one element's symbol and atomic mass are shown, you answer once, and a hard countdown (as low as 10 seconds at the hardest difficulty) forces the next question before you can second-guess yourself. About as close to a literal Buzzer question as an existing game gets — worth looking at directly for how it paces a single timed answer.

Your team doesn't have to build a geography, math, or chemistry question type specifically — the point is the design move: pick a real subject, imagine the person who'd actually use this in their classroom or field, and design the interaction (and the scoring) around how that subject is really taught and thought about, not around what's easiest to implement.

**Scope:** each new question type is a full vertical slice through the system. You are expected to figure out everything that needs to change — the list below gives examples of the kinds of things involved, not a complete checklist:

- Database schema changes if the type needs them (migration required when so)
- Backend validation and scoring logic
- Player interface: rendering the question and capturing the response
- Host interface: question state and real-time answer status
- Admin interface: creating and editing questions of the new type
- Export/import JSON schema support
- Integration tests (T5) and sample games (T6)
- When extending Question's authoring paths, check whether update enforces the same structural validation as create. Don't assume they're symmetric.

### T8 — Image Support in Questions

**Goal:** add the ability to upload images and use them within questions. Images are stored entirely in the database — not on disk or in a separate file store.

| Requirement | Description |
|------------|-------------|
| Upload | Images can be uploaded through the admin or host interface and stored in the database. |
| Question prompt | An image can appear in a question prompt alongside text. |
| Question options | An image can serve as a question option (e.g., multiple choice where the choices are images). |
| Canvas integration | Images can be placed on a canvas-type question (T7), enabling e.g. click-a-region-of-an-image answers. |
| Management | Images can be viewed, replaced, and deleted through the interface. |

As with T7, the full scope of what must change is yours to determine: schema/migration, upload and retrieval endpoints, editor UI, player/host display, integration tests (T5).

### T9 — UI Look-and-Feel & Theming

**Goal:** the starter's UI is functional but visually rough: all three apps hardcode a single dark palette, and raw Tailwind color utilities are scattered through the components. Replace this with a deliberate visual design built on a proper theme system, offering both a **light** and a **dark** theme.

| Requirement | Description |
|------------|-------------|
| Design tokens | Introduce a semantic color-token layer (CSS variables mapped into each app's Tailwind theme — e.g., `surface`, `text-primary`, `accent`, `danger`). Components consume tokens; raw palette utilities are eliminated outside the token definitions. |
| Light and dark themes | Both themes fully cover all three apps — every page usable and intentional-looking in each, no leftover hardcoded colors. |
| Toggle and persistence | Each app has a visible theme toggle. First visit follows the OS preference (`prefers-color-scheme`); the choice persists across reloads. |
| Accessibility | Text meets WCAG 2.1 AA contrast (4.5:1 for body text) in both themes; interactive elements have visible focus states. |
| Context fit | Player stays thumb-friendly on mobile; the host screen is readable from the back of a classroom in both themes; admin remains information-dense but scannable. |
| Evidence | Before/after screenshots of key screens in both themes committed to `docs/ui/` and referenced in your individual markdown document (T10). |

Your new surfaces from T7 and T8 (question editors, canvas question, image management) must be themed too.

### T10 — Individual Markdown Document

**Goal:** each team member creates a personal `docs/<your-netid>.md` with the following sections, each with substantive explanations (not one-liners):

**Repository and Codebase Organization** — describe in your own words how the repository is organized, how the major components relate, and how data flows through the system during a typical game round (host starts a question → player submits an answer → results). Reference the directory context files your team produced (`README.md` or `CLAUDE.md`, whichever your team used) — which you wrote, and what you learned writing them.

**Design Process (Elephant/Goldfish)** — your experience following T3: how the Elephant session produced the design document, what the Goldfish revealed that the Elephant missed, and how the document changed as a result. Link your `docs/design-<feature>.md`. Reflect on whether the process changed how you approached implementation.

**AI Tools Used** — every AI tool you used. For each: a reference to the session log, what you asked and how you used the output, and an honest assessment of where it helped and where it fell short.

> **Session log note:** Claude Code sessions are logged automatically to `ai_log/`. For other AI tools (ChatGPT, Gemini, Copilot, etc.), export your conversation to a file in `docs/` (e.g., `docs/<your-netid>-chatgpt-session.md`) and reference it here.

**Best Practices Learned** — what you learned about professional software development from this project: version control, CI/CD, working in an unfamiliar codebase, role-based design, testing strategy, or effective AI use.

### T11 — TA Code Review

After the deadline, your team will attend a code review with a TA.

1. Every team member attends and participates.
2. Be prepared to walk through **any** part of your team's submission — explain what it does, why it was designed that way, and how you verified it works. You are expected to demonstrate knowledge of the work you submitted, whether you typed it or an AI did.
3. Review your grade report before the meeting. If the automated grading contains any errors, **this is where you raise and address them** — bring the specific rubric item, what the report says, and the evidence it got wrong.

## Submission

By the deadline, all of the following must be true:

- [ ] All work is merged to `main` via approved merge requests.
- [ ] Each member's `docs/<your-netid>.md` is present on `main`.
- [ ] All quiz JSON files are in `sample_games/` on `main`.
- [ ] Theme screenshots are in `docs/ui/` on `main`.
- [ ] Claude Code session logs are in `ai_log/`; logs from any other AI tools are in `docs/` and referenced from your individual document.
- [ ] No force-pushes to `main` after the deadline.
- [ ] Your team has scheduled its TA code review (T11).
- [ ] If your team's composition changed during the project, mention it at your TA code review (R12).

**Optional**: Before submission, test a completely fresh git clone (clone the repo in a different folder) using only the README's steps. Also verify the nginx-built version (npm run build, then localhost:8080) at least once — some behavior (admin→host links, WebSocket) only works there, not under npm run dev.
