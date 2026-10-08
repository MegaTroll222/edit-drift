# Running Nano Banana 2.1 as a multi-turn conversation

Contributed by [Tom Beckenham](https://github.com/tombeckenham) ([PR #1](https://github.com/MegaTroll222/edit-drift/pull/1)).
Results: [`results/milk/nano-banana-2.1-multiturn/`](../../results/milk/nano-banana-2.1-multiturn/).

The main Nano Banana 2.1 run sends each edit as a separate request and re-uploads the previous
output every time. Google's documentation recommends multi-turn conversation as the way to iterate
on images, so this variant runs the whole chain as **one server-side conversation**: the model keeps
the original photo and its own previous outputs in stored state, and nothing is round-tripped
through our side after step 1.

## How to run it

This repo does not ship provider code. To reproduce with your own Google access:

1. Get a Gemini API key from Google AI Studio and install Google's Gen AI SDK for your language.
2. **Turn 1:** start a stored interaction with the model `gemini-nano-banana-2.1`, image output
   only, and send two parts: the benchmark photo (`benchmarks/milk/original.jpg`) and the
   `instruction` of step 1 from `benchmarks/milk/steps.json`. Save the returned image as `step01`.
3. **Turns 2–40:** for each next step, send **only that step's `instruction` text**, chained to the
   previous turn with `previous_interaction_id`. Do not re-upload any image. Save each returned
   image as `stepNN`, exactly as the API returns it.
4. If a turn returns no image or a transient server error, retry the same turn. Don't move on to the
   next step until it succeeds, so the chain stays unbroken.
5. Record the 40 interaction ids and your settings in the run's `meta.json`, then score:
   `editdrift score benchmarks/milk results/milk/<your-run>`.

## What was checked

From the contributor's notes, to make sure the result reflects the model and not the plumbing:

- **Output format:** the API returns JPEG at effectively quality 100; PNG output is not offered on
  the developer API. The block texture is in the generated pixels, not the delivery encoding.
- **Files API instead of an inline upload:** same input token count, score within run-to-run noise.
- **Lossless PNG input instead of the JPEG:** score within the same noise band.
- **Input resolution hint:** not supported for this model.
- **Model-generated starting photo** (no JPEG uploaded at all): the block texture still appears by step 10.

## Result

| Run | Edit Fidelity Score | Mean drift | Final drift |
|---|---|---|---|
| Nano Banana 2.1, separate requests | 54.9 | 45.1 | 92.8 |
| Nano Banana 2.1, multi-turn conversation | 48.5 | 51.5 | 73.3 |

Multi-turn drifts faster over the first 10 edits, then flattens: it finishes lower but averages
slightly worse. It does not move Nano Banana 2.1 up the leaderboard.
