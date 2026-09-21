# Settings and assistant UX — issue #24

Goal: retire the JEV workbench surface, move optional connections into Settings,
and make the review assistant's observed execution state clear and reliable.

Non-goals: no trading execution, no automatic Champion promotion, no new runtime
dependencies, no changes to default chat provider, no removal of research APIs.

Implementation (five repair cycles maximum):
- [ ] Add regression tests for key isolation/validation/probing and stream failure.
- [ ] Add a root-scoped JEV credential module and protected Settings endpoints.
      Only an explicit test sends a synthetic typed question to TypeSafe.
- [ ] Extract Agent integrations from JevView, remove the standalone route, and
      add JEV / Agent Settings sections. Distinguish configuration from connection.
- [ ] Add a compact event-driven assistant activity card; keep tool output folded,
      preserve partial replies, guard concurrent requests, cancel backend turns,
      handle IME and respect the reader's scroll position.
- [ ] Run Python suite/doctor, frontend tests/typecheck/build, Playwright UI checks;
      rebuild committed web assets and submit a linked PR without merging.

Review focus: preparation failures; stop during session creation; stale session
loads; HTTP/SSE errors and truncated streams; credentials leaking through error
messages; remote workbench access. All validation uses synthetic data.
