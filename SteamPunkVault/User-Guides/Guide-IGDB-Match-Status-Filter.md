---
title: "Guide: IGDB Match Status Filter"
date: 2026-05-09
tags: [user-guide, igdb, library, filter]
story: "[[US-022: IGDB Match Status Filter]]"
---

## Overview

The library page has an **IGDB** filter row that lets you instantly narrow the view to games that have (or haven't) been matched to an IGDB entry. This is useful for auditing metadata coverage and deciding which games to investigate.

## Prerequisites

- Library populated with at least one synced platform

## Step-by-Step

### Using the IGDB filter

The IGDB filter row sits below the platform pills on the library page:

| Pill | Shows |
|---|---|
| **All** (default) | Every game regardless of IGDB status |
| **Matched** | Only games with an `igdb_id` (IGDB metadata available) |
| **Unmatched** | Only games with no `igdb_id` (no IGDB match yet) |

Click a pill to apply the filter immediately. It composes with the platform filter and the search box — for example, selecting **Xbox** + **Unmatched** shows only Xbox games with no IGDB match.

### In card view

Filtering is applied client-side — the grid updates instantly without a network request.

### In list view

Filtering is applied server-side — the table re-fetches from the API with the filter applied.

## Troubleshooting

**Filter shows fewer games than expected after an IGDB sync**
: The library page was rendered before the sync completed. Reload the page to get the updated `has_igdb` state for each card.
