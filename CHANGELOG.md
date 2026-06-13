# Changelog

## [0.3.0](https://github.com/ajanderson1/whatsapp_chat_autoexport/compare/v0.2.0...v0.3.0) (2026-06-13)


### Features

* add SpecFormatter for transcript.md generation per WhatsApp Transcript Format Spec ([31b101c](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/31b101cebea02cd953264dfbd60fb8f694f3d63d))
* **cli:** add --keep-drive-duplicates opt-out flag ([eb6b8f0](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/eb6b8f00ed02f81a342f647aab9b1bbea4279658))
* **config:** mirror cleanup_drive_duplicates flag into Settings ([8351591](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/83515915727a77db49829b907a7915196090adb5))
* **discovery:** ContactsContract reconciliation for missed 1:1 chats ([7c946d5](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7c946d5e8df19bd9aca9c7f5cf006d48388cb463))
* **discovery:** reliable chat enumeration with ContactsContract reconciliation ([7aeef58](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7aeef582a3f62cbf6cd9e3c51298f0cb0a319690))
* **drive:** add delete_sibling_exports passthrough on GoogleDriveManager ([7a60800](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7a608006c682280bbf5af39ebea390ab13e92603))
* **drive:** count stale 404 on delete as cleanup success ([12b6f2d](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/12b6f2dd1c59d019ae3420eb44fec743e603b203))
* **drive:** delete_sibling_exports matches base name and .zip variant ([42b0b35](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/42b0b3533b579c83c0c1013035b0f2b71e036d61))
* **driver:** add is_community_chat() upfront probe ([03e7f35](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/03e7f35f5ee7997390074227fdb301bf97fadd1e))
* **driver:** expose wait_for_whatsapp_foreground on WhatsAppDriver ([99b767f](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/99b767f8b7532df7c3164684f03446ddb6aee624))
* **export:** add wait_for_whatsapp_foreground settle helper ([38bc641](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/38bc641aebc4cd05b45f359a5a6c7e674f105836))
* **export:** tri-state ExportOutcome with upfront community detection ([625b7a1](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/625b7a135137b6cd904d7a3b4022abe220cffe44))
* **pipeline:** add cleanup_drive_duplicates config flag (default true) ([b6cbf9b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/b6cbf9bcb4f6b65f43bc240a7966353e7d42366b))
* **pipeline:** call drive cleanup after successful download (gated by flag) ([3a67dd4](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/3a67dd4502dead6d6b370a55d5402430b7a5826e))
* **preflight:** add --skip-preflight CLI flag ([7b30177](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7b3017720b1f9aa34e442ffd6d07add73b41dfd9))
* **preflight:** add Drive OAuth + storage probe ([12667c5](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/12667c57c0d814cfc0ab5ca7564895d25c58d884))
* **preflight:** add ElevenLabs subscription probe ([de0320c](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/de0320cd4c696aadbf745b501b09b9e5e1457c4e))
* **preflight:** add httpx as explicit dependency ([763d67d](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/763d67da5b1794b65ffa4c166da99ffc5d359dff))
* **preflight:** add PreflightPanel Textual widget ([ff43ede](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/ff43ede916e254c436d90e9ff93e0451d3bfb8bf))
* **preflight:** add run_preflight() runner ([33e1e10](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/33e1e106dc7aa3fbffb5235304bcf016827741d6))
* **preflight:** add Status enum, CheckResult, PreflightReport ([524ae1c](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/524ae1c1a7298043c35f56b182b62a27e2bd956f))
* **preflight:** add stderr formatter ([9ac0129](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/9ac0129764f9a344be78186f299dcb172e378cc5))
* **preflight:** add Whisper key-validity probe ([9fcebaa](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/9fcebaac76a3832aef771e5055d19e95a3e45752))
* **preflight:** API credential capacity checks before each run ([fee03a0](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/fee03a0a297909f0ce0e4115bb660fa8465ab74e))
* **preflight:** gate run_headless on preflight result ([cfbe22b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/cfbe22b5b34aa0e28018067e6901bec272e5f4b6))
* **preflight:** gate run_pipeline_only on preflight ([22e5c57](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/22e5c57d1bc37c934332731553385b27b5942681))
* **preflight:** whisper probe surfaces key …last4 + OpenAI org id ([#26](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/26)) ([c32ae4b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/c32ae4bef4ec956e30eb95bcf4d02dc4c5b99e98))
* **spec-formatter:** add format_index method for index.md generation ([ec99f73](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/ec99f738ac046274c3c982ae7dd8ed7cdd6a3099))
* **testing:** C1 connect-verify harness for self-verification loop ([b0041db](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/b0041dbe7f70e84d0d00f5e468fcb76076aefd32))
* **tui:** ChatListWidget stores per-chat status reason ([419a5ff](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/419a5ff3651371b286b3aa6fbd4b1500c4738a1c))
* **tui:** mount PreflightPanel in ConnectPane with gated Connected emission ([e32b094](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/e32b094de110119bfb7e44d8ec7549bcb4295820))
* **v0.3.0:** Phase 1 foundation — app state, version detection, auth status ([2aba72a](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/2aba72aa310cbc41d0e619223be610f605a7287e))
* **v0.3.0:** Phase 2 — Settings panel Google Drive section ([da98657](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/da98657fd13b0180c322f46c6b7ec1a2a9af9a4c))
* **v0.3.0:** Phase 3+4 — prerequisite banners + hard gate on Start Export ([60024a0](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/60024a0bf7f8b03a518b97ad119a86927cc787cf))
* wire --format spec through CLI, pipeline, and headless ([ce45693](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/ce456938c460d7d5ba7d2b3b1489ed283ce79148))


### Bug Fixes

* body_sha256 now hashes formatted body, not raw content ([2f4fde8](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/2f4fde8019b1971bfe45376cf100939f3d8f4cbd))
* **cli:** construct SpecFormatter per-chat in sync/ingest/migrate/rebuild ([#34](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/34)) ([0d89857](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/0d898579083081ba18a6fb0f3d92c0bf18d279c6))
* **discovery:** 2-pass union + dedup + faster scrolls for reliable chat enumeration ([7c436ea](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7c436ea847389d2aa020e52b6b15e46307891d94))
* **drive:** raise cleanup pageSize to Drive API max (1000) ([ef75019](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/ef75019cb0b9f09c7e78b8351af389212ef4a7ad))
* **drive:** serialize GoogleDriveClient access with threading.Lock (F1) ([#19](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/19)) ([0625fc8](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/0625fc8ed30a56a3db5f43532e8bc6898a69f277))
* **export:** settle-wait for WhatsApp foreground before pre-export verify ([145ec93](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/145ec9393ea5fb921d3c5860c78334e338cae974))
* **output:** construct SpecFormatter per-chat in OutputBuilder ([#32](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/32)) ([8430f60](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/8430f60e40dc92d6a3b97b89220c09539b6f9392))
* **pipeline:** pass format_version=legacy in legacy output path ([#39](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/39)) ([96e6574](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/96e6574e7de69862fc09d72d829035c7a6b011c7))
* relax verify_whatsapp_is_open for WhatsApp 2.26 Material 3 ([#27](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/27)) ([#28](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/28)) ([e589d43](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/e589d4379e40d3629cc5e80577c7cd558dcff37b))
* resolve verify race, community skip, and failure visibility from 2026-04-16 run ([340b864](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/340b864795380db2b2d40ca0a496173e479547e3))
* **testing:** C1 harness must use project Logger, not stdlib ([2aef4fc](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/2aef4fcd816adc7f812bfe3f6990861dd540e8c1))
* **tui:** plumb reasons and reconcile chat list at end of run ([4ce4bf6](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/4ce4bf6c64eb5bb0cd99d3f4f7b93050e4e5ace7))
* **tui:** resolve PreflightPanel on main thread before preflight worker ([7e6d074](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7e6d074cbb19dc1e5b62c04f1b1f87d00aef7e22))
* **tui:** restore orphaned progress log line in _skip_chat_export ([f76f580](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/f76f580a7b0f5e0cb836a85ddd764372bb7f3f4b))
* **tui:** route community chats to skip, handle ExportOutcome tri-state ([181f24b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/181f24b8460ebec0b130fbf8cbbd52d1d6d6a285))
* **tui:** settle-wait before verify in TUI export path ([489b528](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/489b52887df52ec9b632b50ab6be500c18428008))
* **v0.3.0:** fetch Drive user email via Drive API instead of id_token ([60f4f93](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/60f4f93e57690ae7365bc17a87024d0ab017cf25))


### Refactors

* **selfverify:** apply code-quality cleanups from review ([53e209e](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/53e209e89b8bc3abce71220ab7af9fa566b8c797))


### Documentation

* add failure report and resolution plan for 2026-04-16 run ([087631e](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/087631ec76b00b7a673b3ebd93631357510c2680))
* add implementation plans for sync service and --format spec ([4d5a7fe](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/4d5a7fe3fdb815c06827bbd78b5729433c678ee5))
* add v1.0.0 roadmap, v0.3.0 Drive integration plan, and phone-local export discovery stub ([d1b73fd](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/d1b73fd87ea96ca2b26813d9ee53249595820afa))
* add WhatsApp Sync Service design spec ([8388ee1](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/8388ee1b1fa236da4e9fae29bebb0632b223e7ea))
* document --keep-drive-duplicates flag and default cleanup behaviour ([2f93197](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/2f93197b69978bfe441cb4eb1608f8cdba01754c))
* document --skip-preflight flag and credential preflight behaviour in CLAUDE.md ([19f0179](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/19f0179a037585954b055042320c1e93c7cf920c))
* **pipeline:** document Drive cleanup step in process_single_export ([a3d145a](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/a3d145adad8cf6db44ab8436857156aa938c9a86))
* **pipeline:** fold Drive deletion into step 1 in process_single_export docstring ([d22736f](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/d22736fb38aed10d7860891719a55e6d0534a90b))
* **plans:** add Drive duplicate cleanup implementation plan ([3a2bbcf](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/3a2bbcf7ed988a4cfc419fb67748bb770360aa0a))
* **plans:** CLI cleanup & subcommand restructure implementation plan ([dd2537a](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/dd2537a03d4a082a5935278c1e7923c1d8e130bc))
* **plans:** convention alignment implementation plan — five-PR train ([60ca7c2](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/60ca7c265872e00386074de27b9629d68312afc5))
* **plans:** preflight implementation plan ([e64a13b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/e64a13bc154f233e8893a987514d8bdacae90583))
* **specs:** add Drive duplicate cleanup design ([f66cff6](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/f66cff6c6db4bc58edff894fcbb3ab5a9419c1ee))
* **specs:** clarify gitleaks install path in PR 4 ([7749045](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/7749045a99ce75548c5b2bb78c121f7dcd191db6))
* **specs:** CLI cleanup & subcommand restructure design ([dc1451f](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/dc1451fd43ea5fb26a32e965d366a51c4a3ee25f))
* **specs:** convention alignment design — five-PR train ([9a89347](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/9a89347837e659ecf7edb0e8827a8f1512d6a8bc))
* **specs:** preflight credential capacity check design ([540b6e3](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/540b6e342acaceb87c06f5ea7a4a763d6b5eff5f))
* **testing:** design for agent self-verification loop ([5e1cac8](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/5e1cac8edd5c3d4b0ce1033a7ff0542ee9f2011f))
* **testing:** fix grc usage-hint path + correct plan's --skip-drive-download note ([a13814b](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/a13814b47ab343d060a62d2f4946f5dd42224f65))
* **testing:** implementation plan for self-verification loop ([b6e9f7d](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/b6e9f7d0a4f8cd2342203ccdb1e68e15ddc483aa))
* **testing:** TESTING.md self-verification loop guide + AGENTS.md ref ([d374bd7](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/d374bd721248b65bc33dc16a77fc24def90166d0))


### CI

* bootstrap release-please + release.yml at v0.2.0 baseline ([#41](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/41)) ([4aa3c6d](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/4aa3c6d29545a756755994d4e4b87278ee7b091b))
* **release-please:** bump release-please-action v4 -&gt; v5 (Node 24 runtime) ([#49](https://github.com/ajanderson1/whatsapp_chat_autoexport/issues/49)) ([a909cba](https://github.com/ajanderson1/whatsapp_chat_autoexport/commit/a909cba43f8f325fb0433b23801ee83eb44f9dbe))
