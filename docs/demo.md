# Recording a demo

How to record a short demo of Paideia, and how the one at the top of the
[README](../README.md) was made.

The moment to show is the project's point: **you add material, and the
environment improves itself.** Everything else in the demo leads up to the
second upload, and the update report it ends with.

## A separate stack for the demo

Record against a database of its own, so the dashboard shows only the demo,
and your own environments stay out of the frame. With Postgres and Redis up
(`docker compose up -d`), create the database once:

```sh
docker compose exec postgres createdb -U paideia paideia_demo
```

In each terminal below, from the repository root, first point the app at the
demo's own database, data folder, Redis database and ports:

```sh
export DATABASE_URL=postgresql+psycopg://paideia:paideia@localhost:5432/paideia_demo
export DATA_DIR=data/demo
export REDIS_URL=redis://localhost:6379/13
export CORS_ORIGINS=http://localhost:3200
```

Then, with the virtual environment active:

```sh
cd api && alembic upgrade head && uvicorn app.main:app --port 8200   # terminal 1
cd api && python -m app.worker                                       # terminal 2
cd web && NEXT_PUBLIC_API_BASE_URL=http://localhost:8200 pnpm build && pnpm start --port 3200   # terminal 3
```

Open http://localhost:3200. The page is built against the demo's API, so it
must be rebuilt with your usual address before `pnpm start` serves
development again; `pnpm dev` is not affected.

## The material

The lectures in [`evaluation/corpus/`](evaluation/corpus/) were written for
this project, so they can be shown freely. To turn all ten into PDFs, from
`api/`:

```sh
python -c "
from pathlib import Path
from evaluation import corpus
out = Path('../data/demo-pdfs'); out.mkdir(parents=True, exist_ok=True)
for doc in corpus.documents():
    (out / doc.filename).write_bytes(corpus.to_pdf(doc.text))
"
```

They land in `data/demo-pdfs/`, which git ignores.

Pick two lectures for the demo:

- **The README's demo** used CPU scheduling, then deadlock. Each brings its
  own concepts and stages, but no relationship crosses the two, because
  neither names the other's concepts.
- **To show the map linking lectures,** use two whose passages name each
  other's concepts. The scheduling lecture names processes 34 times, so
  processes and threads, then CPU scheduling, is likely to show
  relationships that cross the two. That pair was not recorded.

## What to show

About two minutes, in this order:

| Time | Show |
|---|---|
| 0:00 | The dashboard. Create an environment, "Operating Systems". |
| 0:10 | Materials: upload the first lecture. Its steps run one by one: reading, its summary, the environment's summary, concepts, map, roadmap. Speed up the model's part and say so on screen. |
| 0:30 | Summary: open a key point's citation, and the passage shows highlighted in its page. |
| 0:45 | Knowledge map: pick a concept, and see what it builds on, what builds on it, and its parts. |
| 1:00 | Roadmap: the stages, in order, each concept with its passages. |
| 1:10 | Practice: prepare the first stage, then answer two items, one of them wrong. Each answer shows its source and when the concept comes back. |
| 1:25 | **Materials: upload the second lecture.** While it runs, the steps fill in. When it is done, read the update report: the concepts and relationships it added, the pairs the model was not asked again, the stage titles kept, the practice kept. |
| 1:50 | Overview: today's plan, now with the missed concepts first and the new lecture to skim. |
| 2:00 | Search: a question in everyday words, the best passage shown in its page, then "Show scoring". |

## Recording

- **Use a browser window of 1280 by 800** in the light theme, with nothing
  else on screen.
- **On a Mac, Cmd+Shift+5** records a window or part of the screen. Any
  screen recorder works.
- **Say on screen when time is sped up.** The model's work takes minutes, and
  a demo that hides that would misrepresent it.

## Making a GIF

A GIF plays inline in the README on GitHub. Keep it short (about 20 seconds),
about 960 pixels wide, at 10 frames a second, and under a few megabytes.

With ffmpeg, cut the recording into parts, speed up the waits, and convert
it with a palette made from the video itself:

```sh
ffmpeg -i demo.webm -loop 1 -i label.png -filter_complex "\
[0:v]split=3[v1][v2][v3];\
[v1]trim=1:6,setpts=PTS-STARTPTS[a];\
[v2]trim=6:175,setpts=(PTS-STARTPTS)/20[b0];\
[b0][1:v]overlay=(W-w)/2:H-h-28:shortest=1[b];\
[v3]trim=175:177.3,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=5[c];\
[a][b][c]concat=n=3:v=1:a=0,fps=10,scale=960:-1:flags=lanczos,split[s0][s1];\
[s0]palettegen=max_colors=128:stats_mode=diff[p];\
[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" demo.gif
```

The filter does four things:
- It keeps seconds 1 to 6 as they were.
- It plays seconds 6 to 175 twenty times faster, under a label.
- It holds the last frame for five seconds.
- It turns the result into a GIF.

`label.png` is a small image saying "sped up 20×". Some ffmpeg builds can
write the text themselves, with `drawtext`. Change the times to match your
recording.

## How the README's demo was made

- **The stack:** a separate stack like the one above, with the real local
  model (ministral-3:8b on an Apple M3 Pro). Nothing in it was staged or
  edited.
- **The script:** a Playwright script, kept outside the repository, drove the
  page. It created the environment, uploaded "Lecture 2 - CPU scheduling.pdf",
  prepared practice for two stages and answered a session.
- **The recording:** Playwright recorded the second upload, "Lecture 4 -
  Deadlock.pdf", at 1280 by 800, from the upload until the update report.
  That took 172 seconds, 167 of them the model's work.
- **The GIF:** the command above turned the recording into a 21-second GIF of
  2.4 MB, with the model's work sped up twenty times and labelled.
- **The screenshots:** taken from the same environment at twice the
  resolution, then cropped.

## Afterwards

To remove the demo's data, stop its three processes. Then:

```sh
docker compose exec postgres dropdb -U paideia paideia_demo
docker compose exec redis redis-cli -n 13 flushdb
rm -r data/demo data/demo-pdfs
```
