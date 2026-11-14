# 18. Background processing

Date: 2026-11-14
Status: accepted

## Context

Reading documents, embedding them, and everything the language model
writes take seconds to minutes:

- summaries;
- concepts;
- the knowledge map;
- roadmap titles;
- practice items.

Until now all of it ran in the API process, as background tasks queued by
each request and run after the response: 22 of them across 7 routers.

The roadmap asks to move this work out of request lifetimes only once there
is a demonstrated need:

- background jobs through Redis and a lightweight worker;
- a jobs table with status, progress percentage, error message and retry
  count;
- the states queued, running, succeeded, failed and cancelled;
- a frontend that follows job status;
- no Celery unless a concrete requirement appears.

## The need

Phase 17's checks restarted the API several times, and each restart lost
the work in progress:

- summaries stayed "generating" until the one-hour stale rule freed them;
- update records stayed "running" forever.

Every `--reload` during development does the same. There was no retry, no
way to cancel, and the model's work competed with requests inside the web
process.

## Decisions

### Postgres is the queue; Redis wakes the worker

Each job is a row in `jobs` (migration 12), holding:

- its kind, environment and title;
- its lane;
- the steps it runs;
- its status, progress (0 to 100) and the step it is at;
- an error message;
- its attempts and maximum attempts;
- when it may run again;
- a heartbeat, its worker, and timestamps.

Queuing a job inserts the row, then pushes its id to a Redis list for its
lane. The worker waits on that list, and also looks at the table every five
seconds whatever Redis says. A lost signal, or Redis being down, only slows
pickup; it never strands a job.

The worker is the project's own, about 150 lines (`app/worker.py`):

- Celery is ruled out by the roadmap.
- RQ and arq were rejected: both keep their own job state in Redis, which
  would duplicate the table the roadmap asks for, and arq is built for
  asyncio while the services are synchronous.

### Two lanes

The **read** lane reads documents. The **model** lane does everything the
language model writes. The worker runs one thread per lane, so a document
being read never waits behind model work, and model calls stay one at a
time.

A document's chain (added, read again, a new version) becomes two jobs,
both linked to its material update (record 17):

1. reading it;
2. once that has ended, everything derived from it.

A deletion is one model job. Each rebuild requested by hand (a summary,
concepts, the environment summary, the knowledge map, roadmap titles) and
each "Prepare practice" is one model job, practice with one step per
concept.

A job's steps are stored as names and arguments from a fixed registry
(`STEPS` in `app/services/jobs.py`), never as code. They call the same
functions the background tasks called, and steps that carry out a material
update still record themselves on it.

### How jobs end, and retries

- **Succeeded:** every step ran.
- **Failed:** a step recorded its own failure where it always has, such as
  an unreadable PDF or the model being unreachable. The job takes that
  message, for example "Reading the document: This PDF is damaged and could
  not be opened." Trying again from the page starts a new job.
- **Retried:** a job that crashes, or whose worker stops (no heartbeat for
  two minutes), is run again. It waits 30 seconds, then 2 minutes, up to 3
  attempts, then fails. Each step is marked done as it completes, so a job
  run again starts at its first step not done. The worker's own thread
  keeps its running jobs' heartbeats fresh every ten seconds, so a long
  model step is never taken for a stopped one. It looks for stopped
  workers' jobs every minute.

### Stopping and cancelling

- **Stopping the worker** (Ctrl+C or a stop signal): it finishes the step it
  is on, then puts its job back in the queue, not counted as an attempt. The
  next worker carries on from the first step not done. The first version
  trimmed the finished steps instead, so the progress bar jumped back to 0%
  after a stop, and a crash retry ran the job again from its start; marking
  steps done fixed both.
- **A worker that is killed instead** leaves its jobs running until their
  heartbeat is stale; then they are run again.
- **Cancelling a queued job** ends it at once, with any job waiting for it
  and the material update it carries out (which gains a cancelled status).
- **Cancelling a running job** asks it to stop before its next step. A model
  call already in progress finishes first.

## The API and the pages

| Endpoint | What it does |
|---|---|
| `GET /api/environments/{id}/jobs` | An environment's jobs, queued and running first. |
| `GET /api/jobs/{id}` | One job. |
| `POST /api/jobs/{id}/cancel` | Cancel a job. |
| `GET /health/worker` | Whether a worker is running, from the worker keys it keeps in Redis with a 30-second lifetime. Answers 503 with what to do. |

The header shows Worker beside API, Database and Model, checked every half
minute.

Every environment page shows its background work:

- each queued or running job, with a progress bar, the step it is on, and
  Cancel;
- "Stopping after this step…" once cancelled;
- a job being tried again, with why and when;
- jobs that failed in the last hour, with their message.

The strip checks every second and a half while anything is active, and
when work finishes, everything the page shows is asked for again. When jobs
wait and no worker is running, it says how to start one.

Development now runs three processes: the API, the worker
(`python -m app.worker`) and the web app.

## Testing

- **Without Redis or a worker.** Tests run each job in-process right after
  the response (an inline dispatcher), as the background tasks did. All 522
  existing tests passed unchanged with every chain running as jobs.
- **The queue's rules, against Postgres:**
  - oldest first within a lane;
  - a job waits for the one it follows;
  - a crash is tried again after 30 seconds, then 2 minutes, then fails;
  - a stopped worker's job is run again unless its heartbeat is kept;
  - cancelling a queued job ends those waiting for it and its update;
  - a running job stops before its next step;
  - a finished job cannot be cancelled;
  - unknown steps are refused;
  - a stopping worker puts its job back where it was, and the next one
    carries on from the first step not done;
  - the worker runs one job of a lane.
- **The API:**
  - an upload queues reading then deriving, both linked to the update;
  - a step's recorded failure fails the job with its message;
  - preparing practice is one job;
  - finished and unknown jobs;
  - the worker's health;
  - Redis carrying signals and seeing workers, with real Redis where it
    runs, on a database of its own.
- **Deliberate breaks.** Eleven deliberate breaks of the queue's rules were
  all caught, the last being done steps run again. One was first written as
  code that did not parse, which a test run reports as a failure without
  testing anything. The mutation script now refuses those, and it was rerun
  as valid code.
- **In the browser, with the real model and a real worker:**
  - The header showed "Worker ok".
  - An upload was followed in the strip, from "Reading Week 5.pdf" to
    "Updating from Week 5.pdf", through "Writing its summary 14%", "Updating
    the environment summary 28%" and "Extracting concepts 42%", to done.
  - Stopping the worker gracefully during a practice job: it finished the
    concept it was on and put the job back after 22 seconds, not counted as
    an attempt. A new worker completed it, and all 6 concepts were prepared.
  - Killing the worker during another practice job: the next worker found
    the job after 121 seconds ("Its worker stopped while running it. Trying
    again."), and it succeeded on its second attempt.
  - Cancelling a running practice job: the page showed "Stopping after this
    step…", and the job ended cancelled after finishing the concept it was
    on.
  - The page fit a phone's width in the dark theme, with no console errors.

  The check script itself needed fixing twice. On this Mac the worker's
  process is called "Python", so its first search signalled only the
  wrappers. And a new version whose results were all remembered finished in
  11 seconds, too fast to stop in the middle, so practice jobs were used
  instead. The Mac also slept for seven minutes during one run (the lid
  closed); afterwards the worker refreshed its heartbeats before looking for
  stopped workers, so nothing was mistaken for abandoned.

  One wording changed on the way. A knowledge map rebuilt only from
  remembered decisions used to say "The model was asked about 0 new pairs";
  its update step now says "Built from remembered decisions only (N pairs);
  nothing new asked."

## Consequences

- One more process to run. Without it, uploads and model work wait in the
  queue, and the header and strip say so.
- The model's one-at-a-time lock is per process; with one worker, model
  calls stay one at a time. Several workers would need the lock in Redis
  or Postgres.
- A step interrupted by a crash or a killed worker is run again from its
  start; steps already done are not. Every step already checks what is
  done, so running one twice writes nothing twice.
- Retries cover crashes and stopped workers, not failures a step records
  itself, such as the model being unreachable. Those need a person to fix
  the cause and try again.
