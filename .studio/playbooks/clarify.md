# Clarify

## Purpose

Turn an idea into a concise brief and falsifiable prototype hypothesis.

## When to use

Use for `/clarify`, Phase 1, a vague concept, or a prototype without a clear question. Run `studio init` first if project identity is still the placeholder.

## Required inputs

User concept or existing project intent.

## Optional inputs

References, constraints, audience, platform, schedule, and existing artifacts.

## Files to read

`.studio/state/project.json`, `.studio/state/decisions.json`, `.studio/templates/game-brief.md`, and relevant existing design notes.

## State changes

Set current phase to `clarify`, record approved assumptions and prototype hypothesis, and add only blocking user decisions.

## Execution procedure

1. Confirm project identity has been initialized; if not, initialize it without inventing optional engine or platform values.
2. Extract the player fantasy, role, core loop, primary mechanic, target emotion, completion/win and relevant failure conditions.
3. Identify unknowns and assumptions without expanding scope.
4. Form one falsifiable hypothesis connecting mechanic, player behavior, and observable outcome.
5. Define explicit prototype exclusions.
6. Batch only strategic ambiguity for the user; recommend the smallest coherent interpretation.
7. Produce the game brief, update state, and regenerate reports.

## User decision points

Ask about competing fantasies/mechanics, narrative direction, platform, material scope, and what evidence would count as success.

## Outputs

A concise game brief with every required field, an approved or pending falsifiable hypothesis, and a Direction Summary.

## Validation

Check the brief against its template; run `studio validate`, `studio report`, and `studio status`.

## Completion criteria

A falsifiable prototype hypothesis exists. If strategic input is pending, keep the phase open and make the decision the recommended next action.

## Next recommended workflows

`/prototype-plan` after hypothesis approval; `/clarify` again when a blocking decision remains.

## Failure and blocker behavior

Do not manufacture missing creative intent. Record it in the decision queue with options and a recommendation.

## Direction Summary

End with: Current phase; Current milestone; What was completed; What was learned; Evidence available; Important unknowns; Open user decisions; Critical path; Recommended next step; Do not work on yet; Exact next workflow alias.
