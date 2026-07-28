# VisionLearn AI --- Premium UI System Guide

## Mission

Create an interface that feels invisible until needed. The lecture
remains the focus while AI quietly augments learning.

# UX Principles

-   Content first
-   One-click actions
-   Progressive disclosure
-   Consistent spacing
-   Zero unnecessary popups
-   Keyboard friendly
-   Responsive animations
-   Accessibility by default

# Layout

    +--------------------------------------------------------+
    | Browser Toolbar                                        |
    +--------------------------------------------------------+
    |                                                        |
    |  Lecture Slide                 | AI Sidebar            |
    |                                |-----------------------|
    |                                | Ask                  |
    |                                | Concepts             |
    |                                | Notes                |
    |                                | Quiz                 |
    |                                | History              |
    |                                | Settings             |
    |                                |                      |
    +--------------------------------------------------------+

Sidebar: - Default width: 380px - Collapsible - Resizable - Remembers
last width

# Design Tokens

Radius: - 8 - 12 - 16

Spacing: - 4 - 8 - 12 - 16 - 24 - 32

Shadows: - subtle only

Typography: - Inter - JetBrains Mono - KaTeX

# Component Library

Core: - Button - Card - Panel - Tabs - Modal - Drawer - Toast -
Tooltip - Badge - Avatar - Progress

AI: - ChatBubble - AIResponse - CitationCard - EquationCard -
DiagramCard - FigureCard - GraphCard - ConceptCard - QuizCard -
Flashcard

Slide: - ObjectOverlay - HoverOutline - SelectionBox - FloatingToolbar

# Chat UX

Every answer contains: 1 Summary 2 Detailed explanation 3 Related
concepts 4 References 5 Suggested follow-up

# Figure UX

Hover: blue outline

Click: selection

Double click: deep inspector

Inspector tabs: Overview Relationships Raw Extraction Confidence

# Search

Unified search across: Slides Figures Equations Concepts Chats Notes

Supports: recent fuzzy search filters

# Empty States

No lecture No internet No OCR No results

Every empty state includes a helpful next action.

# Motion

Hover 120ms Open panel 180ms Fade 150ms

No bouncing or distracting effects.

# Accessibility

WCAG AA Keyboard navigation Screen reader support High contrast Reduced
motion

# Responsive Rules

Never cover the slide.

When width is small: collapse labels keep icons

# Error UX

Always explain: What happened Why What user can do

# Quality Checklist

Every screen must answer:

Where am I? What can I do? What is selected? What changed? What happens
next?

# UI Review Before Release

-   Pixel consistent
-   No overflow
-   Dark mode verified
-   Loading states everywhere
-   Empty states everywhere
-   Error states everywhere
-   Keyboard shortcuts work
-   Accessible labels present

# Golden Rule

Every interaction should reduce cognitive load. Students should feel
they are studying the lecture---not learning how to use the extension.
