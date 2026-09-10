# Hot Topics Implementation Plan

> Execute inline using the executing-plans skill, with tests before each component.

**Goal:** Add terminal mode 4 with reproducible ranking, comment evidence, local export and DeepSeek summaries.
**Architecture:** Dedicated hot_topics package for configuration, collection, ranking and report/service code. TreeholeClient adds read-only v3 methods; agent.py provides CLI integration.
**Tech Stack:** Python 3.8+, requests, Jieba, unittest; existing DeepSeek transport.
**Spec:** ../specs/2026-09-10-hot-topics.md

## Global constraints
24/72/168 hours, 30 final posts, 5–10 topics when supported, single run; preserve modes 1–3; private files never committed; sample limits visible; no new hosting or scheduled task.

## Task 1: API and collection
Files: client.py, hot_topics/config.py, hot_topics/collect.py, tests/test_hot_collection.py.
Interface: list_recent_posts(page,limit,**request_options), list_hot_comments(pid,page,limit,**request_options) -> raw v3 dict. collect_recent(client,config,now) -> (posts,metadata). collect_comments(client,post,config) -> enriched post.
- [x] Write unittest cases with a fake paginated v3 session, timestamps 100/200/300, duplicate IDs, total mismatch and missing parent IDs. Assert collected IDs and metadata rather than implementation text.
- [x] Run `venv/bin/python -m unittest discover -s tests -p 'test_hot_collection.py' -v`; verify missing behavior fails.
- [x] Add validated dataclass config, explicit v3 request parameters/retries, bounded enumeration, partial-result metadata and ID-based relation resolution.
- [x] Re-run collection tests until passing.

## Task 2: Ranking
Files: hot_topics/ranking.py, hot_topics/stopwords.txt, hot_topics/campus_words.txt, tests/test_hot_ranking.py.
Interface: rank_posts(posts,config,now) -> (selected,keywords).
- [x] Write tests: 3 distinct posts containing 体育课 produce DF=3 even if repeated 20 times in one; isolated 100-favorite post survives union; missing counts remain null; old/future timestamps excluded by collector.
- [x] Run ranking tests and verify missing implementation failure.
- [x] Implement tokenizer/DF, smooth TF-IDF cosine, average positive-metric ranks, explicit thresholds, deterministic tie breaking, topical grouping and score explanations.
- [x] Re-run ranking tests.

## Task 3: Report and replay
Files: hot_topics/report.py, hot_topics/service.py, tests/test_hot_report.py.
Interfaces: run_hot_topics(client,llm,config,now=None) -> result; replay_hot_topics(path,llm,config) -> result. llm(user_message,system_message) -> text or raises.
- [x] Write tests that fake model inspects already-written exports, unknown citations are rejected, failures persist, long comments are chunked without loss and empty results skip model.
- [x] Run report tests and verify missing behavior failure.
- [x] Implement atomic exports, bounded context chunks, quoted parents, hierarchical summary and reproducible offline replay without login.
- [x] Run all tests.

## Task 4: CLI and regression
Files: agent.py, config_example.py, requirements.txt, start.sh, README.md, docs/HOT_TOPICS.md, tests/test_hot_cli.py.
- [x] Write terminal input tests for mode 4, invalid windows, return to menu, and import without private config; existing modes exercised with synthetic client and fake HTTP model boundary.
- [x] Run CLI tests to see failure.
- [x] Add mode entry, lazy package import, CLI flags --hot-only/--hot-replay/--hot-hours, strict model invocation and default config guidance; document deterministic tests and manual acceptance.
- [x] Run `venv/bin/python -m unittest discover -s tests -v` and `venv/bin/python -m compileall -q agent.py client.py hot_topics tests`.

## Task 5: Verification and delivery
- [x] Inspect diff for unsupported API assumptions, count semantics, privacy and backwards compatibility.
- [x] Use local config for limited real probe and selected report; if unavailable explicitly report real verification pending.
- [x] Document results and give concrete local commands for user acceptance.
- [ ] Only after local acceptance push feature branch, open PR to user's main and merge per user instruction.
