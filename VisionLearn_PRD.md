# VisionLearn AI - Product Requirements Document (PRD)

## Executive Summary

VisionLearn AI is a Chrome extension and backend platform that
understands STEM lecture slides by combining OCR, math recognition,
multimodal AI, retrieval, and interactive querying.

## Product Vision

Create an AI tutor that understands text, equations, diagrams, charts
and figures---not just documents.

## Users

-   Computer Science students
-   AI/ML students
-   Engineering students
-   Lecturers
-   Researchers

## Core MVP

-   Chrome Extension (Manifest V3)
-   React + TypeScript sidebar
-   FastAPI backend
-   OCR pipeline
-   Math OCR pipeline
-   Vision-language analysis
-   Vector search
-   Current slide + presentation queries
-   Bounding-box object interaction

## Architecture

Extension -\> FastAPI -\> Processing Pipeline Pipeline: 1. Screenshot
ingestion 2. Layout detection 3. OCR 4. Math OCR 5. Figure
classification 6. Vision analysis 7. Object extraction 8. Embedding
generation 9. PostgreSQL + pgvector 10. Redis cache 11. LLM reasoning

## Database Tables

presentations slides objects embeddings conversations cache_entries

## API

POST /slides/analyze POST /chat GET /presentation/{id} POST /quiz POST
/notes

## UI

Tabs: - Ask - Concepts - Notes - Quiz

Modes: - Figure - Slide - Presentation - General - Auto

## Folder Structure

backend/ frontend/ extension/ services/ models/ prompts/ docs/ tests/

## Sprint Plan

Sprint 1: - Repo - Extension - FastAPI - Screenshot upload

Sprint 2: - OCR - Math OCR - Sidebar

Sprint 3: - Vision - Object detection - Bounding boxes

Sprint 4: - Retrieval - Chat - Presentation indexing

Sprint 5: - Quiz - Notes - Concept graph (basic)

## Non-functional Requirements

-   \<2s cached response
-   Modular services
-   Logging
-   Unit tests
-   Typed APIs

## Future Versions

-   Interactive figures
-   Code generation
-   Knowledge graph
-   Personalized tutor
-   Voice mode
-   Accessibility enhancements

## Claude Code Rules

-   Build incrementally.
-   One milestone per pull request.
-   Never refactor everything at once.
-   Write tests for backend endpoints.
-   Keep services loosely coupled.
-   Cache expensive AI operations.
-   Document every API.
