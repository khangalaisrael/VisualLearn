# VisionLearn AI -- MVP Build Specification

## Vision

Build a Chrome extension that understands STEM lecture slides (text,
equations, diagrams, charts) and allows users to query them
interactively.

## Primary Goal

Deliver a working MVP before adding advanced research features.

## Success Criteria

-   Detect current slide.
-   Capture visible slide.
-   Extract text.
-   Extract equations.
-   Analyze diagrams with a vision model.
-   Answer questions grounded in the current slide.
-   Support presentation-wide search.
-   Highlight the referenced region.

------------------------------------------------------------------------

# Tech Stack

## Frontend

-   React
-   TypeScript
-   Tailwind CSS
-   Chrome Extension Manifest V3

## Backend

-   Python 3.12
-   FastAPI
-   PostgreSQL
-   Redis (cache)

## AI

-   OCR engine
-   Math OCR
-   Vision-language model
-   Embedding model
-   LLM for reasoning

------------------------------------------------------------------------

# Architecture

Extension → FastAPI → OCR → Math OCR → Vision Analysis → Embeddings →
Database → LLM → Response

------------------------------------------------------------------------

# Core Features (MVP)

## Extension

-   Detect slide changes.
-   Capture current slide.
-   Sidebar UI.
-   Click-to-query.

## Backend

-   Upload screenshot.
-   Cache analyses.
-   Object detection.
-   OCR.
-   Math extraction.
-   Vision analysis.
-   RAG over presentation.

## Sidebar Tabs

-   Ask
-   Concepts
-   Notes
-   Quiz

------------------------------------------------------------------------

# Data Model

Object: - id - slide_number - type - bounding_box - extracted_text -
latex - summary - embedding - confidence

Supported types: - title - paragraph - equation - diagram - graph -
table - image

------------------------------------------------------------------------

# Query Modes

1.  Figure
2.  Slide
3.  Presentation
4.  General AI
5.  Auto

------------------------------------------------------------------------

# Roadmap

## Milestone 1

-   Extension scaffold
-   FastAPI
-   Screenshot capture

## Milestone 2

-   OCR
-   Math OCR
-   Sidebar

## Milestone 3

-   Vision understanding
-   Current slide chat

## Milestone 4

-   Presentation indexing
-   Figure queries

## Milestone 5

-   Concept graph
-   Quiz generation
-   Flashcards

------------------------------------------------------------------------

# Out of Scope (v1)

-   Multi-agent system
-   Editable diagram generation
-   Automatic code generation from every diagram
-   Cross-course memory
-   Advanced theorem proving

------------------------------------------------------------------------

# Coding Principles

-   Modular architecture.
-   Cache every expensive operation.
-   Services instead of agents.
-   Strong typing.
-   Unit tests for backend.
-   Clear API contracts.
-   Feature flags for experimental capabilities.

------------------------------------------------------------------------

# Initial Folder Structure

    visionlearn/
        backend/
        extension/
        frontend/
        ai/
            ocr/
            math/
            vision/
            embeddings/
        database/
        shared/
        docs/

------------------------------------------------------------------------

# First Sprint

1.  Create repository.
2.  Scaffold FastAPI.
3.  Scaffold Chrome extension.
4.  Capture current slide.
5.  Send image to backend.
6.  Return placeholder analysis.
7.  Display in sidebar.

Only after this foundation is stable should advanced AI capabilities be
added.
