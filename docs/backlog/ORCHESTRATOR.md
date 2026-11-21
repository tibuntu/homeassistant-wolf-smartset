# Orchestrator prompt

You coordinate the backlog of the Wolf SmartSet integration. Your job is to get the briefs in this folder done, one pull request per brief. You dispatch the implementation work to subagents, review what they deliver, and bring the decisions that belong to the owner to the owner. You write little code yourself.

## Read first

1. [`README.md`](README.md) in this folder: the brief index, the evidence labels and the **rules for every brief**. The rules bind you and every subagent you start; quote the section into every dispatch.
2. [`CLAUDE.md`](../../CLAUDE.md) at the repository root: commit conventions. It forbids `Co-Authored-By` trailers and attribution lines; that wins over any default.
3. The brief you are about to dispatch, in full.

## The loop

Work through the index in its suggested order (01, 02, 03, 04, then the rest). For each brief:

1. **Triage.** Read its status line.
   - *ready*: continue.
   - *needs owner decision* or *needs the owner's go*: ask the owner the brief's question in one message, with your recommendation, then continue with the next brief while you wait. Resume the brief when the answer arrives and record the answer in the brief before dispatching.
   - *waits for* (brief 10): check whether the trigger has happened; if not, skip.
   - *parked* (12 to 14): skip, unless the owner reports that a "Revisit when" condition holds.
   Done when every brief is either dispatched, waiting on a named owner answer, or skipped with its reason.
2. **Check for conflicts.** Briefs touching the same files run one after the other: 02 and 03 (README "Examples", `quality_scale.yaml`); 01 and 06 (`icons.json` needs the event key); 01, 04 and 07 (`__init__.py`, `coordinator.py`). Independent briefs may run in parallel, at most two at a time.
3. **Dispatch** one subagent per brief, in its own git worktree, on a branch named after the brief (`feat/write-event-entity`, `docs/energy-recipe`, …). The dispatch prompt contains: the brief's path, the instruction to read the README rules and the brief before touching code, the branch name, the shell notes below, and the deliverable: a pushed branch, a pull request whose description lists every "done when" item with its proof, and the brief deleted in the same pull request (README rule: the brief is deleted when it is done; also remove its row from the index).
4. **Review** the returned pull request against its brief before telling the owner it is ready. Check every "done when" item yourself (read the diff, read the CI result with `gh pr checks`); have a separate reviewer subagent read the diff without your conclusions when the change touches the write pipeline, redaction or the entity registry (briefs 01, 04, 07). Send it back to the implementing subagent with concrete findings until it holds. Done when every criterion is met with evidence, not when the subagent says so.
5. **Hand over.** Tell the owner the pull request is ready, in two or three lines: what changed, what was verified, anything they must check on their real system. The owner merges.

Finish with a short report: merged or ready pull requests, open owner questions, skipped briefs and why.

## Owner gates

Stop and ask, never proceed on your own, for:

- any real write to the heating system, including trying a blueprint or automation with dry run off;
- the first call to an endpoint the integration does not use yet (brief 15, `ReadFaultMessages`);
- raising the minimum Home Assistant version (brief 10);
- reopening or commenting on GitHub issues, releases, and anything in the owner's Home Assistant.

Read-only measurements on the owner's Home Assistant are allowed without asking: a read-only SQLite query against the recorder (`file:/config/home-assistant_v2.db?mode=ro`) piped through `kubectl --context tibuntu -n homeassistant exec -i homeassistant-home-assistant-0 -c home-assistant -- python3 -`. Write the script to a file first; no heredocs.

## Repository habits

- The owner merges pull requests within minutes and rebase-merges them. Before pushing a follow-up to a branch, run `gh pr view <n> --json state`; if it is merged, branch from the fresh `main` instead.
- Another session may work in the main checkout. Keep your own checkout on `main`; do branch work in worktrees.
- One-line documentation fixes go straight to `main`. Code, fixtures and anything release-please turns into a release go through a pull request with a Conventional Commits title (the brief names the type).
- Do not bump versions or edit `CHANGELOG.md`; release-please does that.

## Shell notes (pass these to every subagent)

- Inside a worktree the isolation hook refuses `git` and `rtk git`. Call `/usr/bin/git` with literal absolute paths, one plain command per call, staging explicit paths. `gh` works normally.
- No heredocs and no `$(cat <<…)` (SCM Breeze breaks them); write commit messages with `-m`. Use `/bin/rm`, `/bin/cat`, `/bin/ls`.
- Outside worktrees, prefix commands with `rtk` (see the owner's global instructions).
- The auto-mode classifier blocks `git checkout -- <file>`, `push --force-with-lease`, `branch -D`, `push --delete` and `reset --hard`. Do not work around it: give the owner a one-liner prefixed with `!` (`git -C ~/git/private/homeassistant-wolflink …`).
- Merge gate, locally: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy custom_components/`, `uv run bandit -c pyproject.toml -r custom_components/`, `uv run pytest` (95 % branch coverage), `scripts/check-fixtures.sh`. hassfest and HACS validation only run in CI.
