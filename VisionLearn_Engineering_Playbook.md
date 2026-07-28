# VisionLearn AI -- Engineering Playbook

## Purpose

This document complements the PRD and focuses on engineering execution,
UI philosophy, architecture decisions, development methodology, and
quality practices.

# Guiding Principles

1.  Build vertical slices, not isolated components.
2.  Every feature must be demoable.
3.  Prefer simple architecture over clever architecture.
4.  Optimize for correctness before speed.
5.  Measure everything.

------------------------------------------------------------------------

# Recommended Development Methodology

## Agile (2-week sprints)

Each sprint should produce: - Working software - Demo video - Updated
documentation - Tests - Performance metrics

Sprint lifecycle: 1. Plan 2. Design 3. Implement 4. Test 5. Demo 6.
Retrospective

------------------------------------------------------------------------

# Git Workflow

main ├── develop ├── feature/* ├── bugfix/* └── release/\*

Commit style:

feat: fix: docs: refactor: test: perf:

Merge only through Pull Requests.

------------------------------------------------------------------------

# Definition of Done

A task is complete only if:

-   Code builds
-   Tests pass
-   API documented
-   UI works
-   Logs added
-   Error handling added
-   Reviewed
-   Demo recorded

------------------------------------------------------------------------

# UI Philosophy

The UI should never overwhelm students.

Main layout:

  -----------------------------------
  \| Toolbar \|
  -----------------------------------
  \| Slide \| Sidebar \| \| \| \| \|
  \| Ask \| \| \| Concepts \| \| \|
  Notes \| \| \| Quiz \|

  -----------------------------------

Never hide the slide.

Sidebar width: 350--420px

------------------------------------------------------------------------

# Primary Navigation

Top:

Presentation Search Settings

Sidebar:

Ask

Concepts

Notes

Quiz

History

------------------------------------------------------------------------

# Interaction Model

Hover → highlight object

Click → select object

Double click → deep explanation

Right click → quick actions

------------------------------------------------------------------------

# Object Actions

Explain

Summarize

Generate Quiz

Generate Flashcards

Copy LaTeX

Copy Markdown

Open References

------------------------------------------------------------------------

# Design System

Use:

TailwindCSS

Rounded cards

Minimal shadows

Readable typography

Keyboard shortcuts

Dark mode

Accessibility first

------------------------------------------------------------------------

# Performance Goals

Capture slide: \<150ms

Cached query: \<2 seconds

Fresh analysis: \<8 seconds

Memory usage: Monitor continuously.

------------------------------------------------------------------------

# Logging

Log:

Processing time

Model used

Cache hit

Errors

Object count

Confidence

Never log private slide content in production.

------------------------------------------------------------------------

# Error Handling

Show friendly errors.

Example:

Unable to recognize equation.

Retry

Report

Use general explanation instead

Never crash the sidebar.

------------------------------------------------------------------------

# Testing Pyramid

Unit Tests

Service Tests

API Tests

Integration Tests

Manual UX Tests

End-to-End Tests

------------------------------------------------------------------------

# Security

Validate uploads.

Limit image size.

Sanitize prompts.

Encrypt stored conversations.

Rate limit APIs.

Never expose API keys.

------------------------------------------------------------------------

# Documentation

Maintain:

README

Architecture

API

Deployment

Developer Guide

Prompt Library

Decision Log (ADR)

------------------------------------------------------------------------

# Architecture Decision Records

Record important choices.

Example:

ADR-001

Why FastAPI?

ADR-002

Why PostgreSQL?

ADR-003

Why object-based indexing?

------------------------------------------------------------------------

# Code Review Checklist

Readable?

Typed?

Tested?

Modular?

Documented?

No duplication?

Good naming?

------------------------------------------------------------------------

# Technical Debt Rules

Never leave TODOs without issue IDs.

Schedule refactoring every third sprint.

------------------------------------------------------------------------

# Observability

Dashboard:

Average latency

OCR accuracy

Math extraction success

Cache hit rate

Failed requests

------------------------------------------------------------------------

# UX Metrics

Time to first answer

Questions per session

Average session length

Repeat usage

Quiz completion

------------------------------------------------------------------------

# Accessibility

Keyboard navigation

Screen reader labels

High contrast

Scalable fonts

Reduced motion option

------------------------------------------------------------------------

# Future Architecture

Keep services independent.

Possible services:

OCR

Math

Vision

Retrieval

Reasoning

Quiz

Notes

Do not split into microservices until necessary.

------------------------------------------------------------------------

# Weekly Deliverables

Week 1 Repository + Extension

Week 2 Backend + Upload

Week 3 OCR

Week 4 Math OCR

Week 5 Vision

Week 6 Query Engine

Week 7 Presentation Search

Week 8 UI Polish

Week 9 Testing

Week 10 Optimization

Week 11 Documentation

Week 12 Release Candidate

------------------------------------------------------------------------

# Final Goal

When a student opens any STEM lecture, VisionLearn should make every
equation, diagram, graph and figure interactive, searchable, explainable
and connected into a coherent learning experience.
