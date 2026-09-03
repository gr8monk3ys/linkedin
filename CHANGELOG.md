# Changelog

## 0.1.0 (2026-09-03)


### Features

* add AIClientError with retry/backoff to AI client, propagate in services ([bcf8554](https://github.com/gr8monk3ys/linkedin/commit/bcf8554550a46d79eef9c7a2d9ec5247e2269b00))
* add ApplicationService with CRUD, pipeline advance, AI resume/cover-letter/skills-gap ([f3fc28f](https://github.com/gr8monk3ys/linkedin/commit/f3fc28f63fc836caf83c7cbff54d05a0caa09474))
* add auto-outcome recording and response tracking to template service ([b9f1c4f](https://github.com/gr8monk3ys/linkedin/commit/b9f1c4f2e0e7afa9aa3c7b623b7d43faa1881193))
* add backup verify and restore to data service ([3cacad6](https://github.com/gr8monk3ys/linkedin/commit/3cacad6302900d85952452c40486bd02c39ac554))
* add campaign management and duplicate detection to contact service ([a1760eb](https://github.com/gr8monk3ys/linkedin/commit/a1760eb5b7020b73812f58aa34344245dc421857))
* add CLI command groups for applications, interview, conversations, calendar ([40fcefd](https://github.com/gr8monk3ys/linkedin/commit/40fcefda41e71ddb16f17201829293c14a351e34))
* add ConversationService and ContentCalendarService with full test coverage ([d40f419](https://github.com/gr8monk3ys/linkedin/commit/d40f419bb6691d486d65c9843a5bed8a7c2a9428))
* add InterviewService with AI-powered prep, research, STAR, questions-to-ask ([5aba778](https://github.com/gr8monk3ys/linkedin/commit/5aba7780ebdb070d125c35040b5ea9412b489ebb))
* add job posting import and skill-match scoring to market service ([09b7294](https://github.com/gr8monk3ys/linkedin/commit/09b7294304cefe34d96980a587f135037bd58464))
* add LinkedIn Playwright scraping — search-and-collect, import-search-results, scrape-profile ([c9c3def](https://github.com/gr8monk3ys/linkedin/commit/c9c3defe798831c1e2defe909c23dbc845afee1f))
* add offline fallback templates to draft service ([10b9d3b](https://github.com/gr8monk3ys/linkedin/commit/10b9d3b8e7cf5a999bdd25bb0f4e7942891c6438))
* add resume_text to profile setup CLI with --resume-file flag, update README with v2.1 commands ([6a96d3a](https://github.com/gr8monk3ys/linkedin/commit/6a96d3ae1bac675a77dbb578c10cd93c09c213d9))
* AI off by choice, and hand-written drafts enter the same pipeline ([#61](https://github.com/gr8monk3ys/linkedin/issues/61)) ([8ba34f5](https://github.com/gr8monk3ys/linkedin/commit/8ba34f55d4172e7b90a1f1008e1c0fa68f3cae03))
* feed engagement with AI-personalized comments ([#43](https://github.com/gr8monk3ys/linkedin/issues/43)) ([09643e4](https://github.com/gr8monk3ys/linkedin/commit/09643e4a5dea98c27790bc85b9d1295876458616))
* foundation — new types, repos, JSON store, factory for applications/conversations/calendar/interview-prep ([cf8fd26](https://github.com/gr8monk3ys/linkedin/commit/cf8fd262ab2d2e8a790408dfe99d45a7ddde515a))
* growth prerequisites — key probe, one headline source, live metrics ([#56](https://github.com/gr8monk3ys/linkedin/issues/56)) ([2ac83c4](https://github.com/gr8monk3ys/linkedin/commit/2ac83c4a1bdc74032cf6e1c292fcc763327f01c8))
* rank contacts by career priority; pinned contacts are exempt ([#55](https://github.com/gr8monk3ys/linkedin/issues/55)) ([bffa315](https://github.com/gr8monk3ys/linkedin/commit/bffa3155866796f6a078716e74128b50ce8e0aad))
* the content engine — public fleet facts, Sunday batch, skip-by-default ([#57](https://github.com/gr8monk3ys/linkedin/issues/57)) ([4b663b6](https://github.com/gr8monk3ys/linkedin/commit/4b663b63afef25d567b6f8940618d0a76c3dd90b))
* wire up LinkedIn automation, resume repo integration, and audit fixes ([#41](https://github.com/gr8monk3ys/linkedin/issues/41)) ([961400a](https://github.com/gr8monk3ys/linkedin/commit/961400a13348e5db7f90f6f32c02bf3c372281f3))


### Bug Fixes

* add linkedin-cli alias and json store tests ([58889aa](https://github.com/gr8monk3ys/linkedin/commit/58889aabe9620697fbdb982cb48487912b10fceb))
* add missing resume_text confirm input to profile setup test invocations ([3f01183](https://github.com/gr8monk3ys/linkedin/commit/3f0118324de329110a01c791f022b2c72d86fa39))
* add resume_text to ProfileDict, fix db_repos fixture to return 9-tuple ([d8bc029](https://github.com/gr8monk3ys/linkedin/commit/d8bc0293c9d6e66fd91c16a417549dac656ae818))
* **ci:** repoint org workflows to the public reusable home ([#39](https://github.com/gr8monk3ys/linkedin/issues/39)) ([462ebfe](https://github.com/gr8monk3ys/linkedin/commit/462ebfeb1b88f3f0d1113b5d4d6a228f1cda5430))
* correct automation profile action detection and expand test fixture ([1b166b8](https://github.com/gr8monk3ys/linkedin/commit/1b166b883dc014be7448157133657f657e642454))
* remove unused imports in test_applications.py ([f5a9c13](https://github.com/gr8monk3ys/linkedin/commit/f5a9c13cc4b7f82cc560bebfa7d8d8a2bb83a41e))
* sort imports in test files to satisfy ruff I001/F401 ([d251a4e](https://github.com/gr8monk3ys/linkedin/commit/d251a4e85e1daf137437cb0e6566c9eea3d5a0e1))
* the doctor reads the launchd job that actually runs the daily plan ([#60](https://github.com/gr8monk3ys/linkedin/issues/60)) ([78cd8d5](https://github.com/gr8monk3ys/linkedin/commit/78cd8d5fddcc884fa220d1c42edcd4a5504496c9))


### Documentation

* update CLAUDE.md to reflect v2.1 features and test structure ([e832fb5](https://github.com/gr8monk3ys/linkedin/commit/e832fb538932e0c41a87805ee97e1e81cd9dda6b))
