# QueryLens

QueryLens is a dark, developer-focused SQL query-plan analyzer and SQLite index-advisor workbench. It combines a zero-build Vanilla JS frontend with Python 3.12 serverless functions and a deterministic, synthetic SQLite benchmark dataset.

## Features

- 15,500 synthetic rows across merchant accounts, M-Pesa transactions, and API request logs.
- Three slow-query presets, SQLite `EXPLAIN QUERY PLAN`, and measured execution latency.
- Read-only SELECT/WITH validation, index heuristics, and optional before/after index comparison.
- Schema explorer, query-plan severity visualization, and sample result preview.

## Deploy to Vercel

Import this repository into Vercel with the project root as the root directory. Vercel detects the Python functions under `api/` and serves the static frontend from `public/`. No Node build step is required.

The API routes are:

- `GET /api/schema`
- `POST /api/explain` with JSON `{"sql":"SELECT ...","applySuggestedIndexes":true}`

## Run locally

The frontend is static and expects the API routes above. For local API development, install the Vercel CLI and run `vercel dev` from the repository root (Python 3.12 recommended).

## Benchmark model and limitations

The database is created in memory for each serverless invocation. This keeps demo data isolated and deterministic, but indexes do not persist across requests or invocations. The comparison endpoint measures baseline and indexed execution within one request. SQLite's query-plan API does not expose exact rows-scanned counters; QueryLens reports plan scan nodes rather than inventing a scan count. Timings are illustrative and depend on the serverless runtime, cold starts, and load.

The dataset is synthetic and contains no real payment or customer information. Do not use this demo database to process production M-Pesa records.

## Security

Only a single read-only SELECT or WITH statement is accepted. DDL/DML, PRAGMA, file/extension functions, oversized requests, and indexes referencing non-benchmark tables or columns are rejected. This is a learning/benchmark tool, not a secure multi-tenant SQL execution service.
