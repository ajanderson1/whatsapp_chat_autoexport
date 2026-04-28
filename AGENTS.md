# Agent Conventions — WhatsApp Chat AutoExport

## Roadmap
GitHub Milestones are the roadmap. The active milestone has the nearest future due date (or the earliest open one if none have due dates). See the GitHub UI for the milestone list.

## Work units
Issues are units of work. Each issue has:
- A `type:` label (feat, fix, chore, docs)
- Optionally a milestone assignment

Backlog = issues with no milestone.

## Branching and PRs
- Branch naming: `feat/NN-slug`, `fix/NN-slug`, `chore/NN-slug`, `docs/NN-slug` (NN = issue number)
- PR body must include `Closes #NN`
- CI must be green; auto-merge is enabled
- One issue → one branch → one PR

## Test discipline
Test-driven development is the default. Use `superpowers:test-driven-development`.

## Orientation
Run `/aj-flow status` to see the repo dashboard: advisories (lost-work risks first), worktrees, open PRs, the active milestone, and top issues to tackle next.

## Resuming work on an existing issue
Run `/aj-flow flow <issue-number>`.

## Filing a new thought
Run `/aj-flow issue <description>`.
