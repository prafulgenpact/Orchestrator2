# Objective (IMMUTABLE — only the human edits this file)

Project: A multi agent orchestrator system calling relevant apps basis intent recognition — It recognises user intent, breaks it down into smaller tasks and then calls relevant APPS to complete the task
Type: agent
Written: 2026-07-03

## What we are building

The engine will take a task as input from the user. The orchestrator breaks the user into multiple chain of tasks - could be sequential or parallel. Then it determines what app needs to be called for what task to be completed. I already have written 11 Apps - Teach Me, Blogs Playground, Coding Playground, Social Media AI, Research Assistant, Stanford LLM, Stats Teacher, Test, ArXiv Papers, Simulated learning, Github learnings. These are all located in Desktop/Desktop folder. The Orchestrator decides what is the relevant app needed to be called for what task. If some task has no relevant app, it fetches the answers from the web. There will be full traceability, auditability of the work the orchestrator will do. Everything will be logged into an observability dashboard which can be presented to leadership.

## Who it is for and why

For my own self ... It solves the purpose of leverulti agent processing of long running tasks

## Acceptance criteria (the definition of project success)

Each criterion maps to at least one automated test (unit or e2e) that proves it.

1. AC-1: UI has to invoke right set of apps at the backend to achieve the task
2. AC-2: the apps can not hang
3. AC-3: Every small feature needs to be tested before saying "done"
4. AC-4: The individual apps are tuned to my style of answering, the orchestrator needs to respect that

## Explicitly OUT of scope

- Nothing

## Constraints

- Never make up stuff
- The answers need grounding and traceability
- User experience is important - that should never be compromised
- Accuracy is the MOST IMPORTANT feature for me .... I can not work with inaccurate results - REMEMBER THIS THROUGHOUT THE DEVELOPMENT LIFE CYCLE
