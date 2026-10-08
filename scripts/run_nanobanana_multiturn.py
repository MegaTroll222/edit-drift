"""Run the milk chain on Nano Banana 2.1 through the Gemini Interactions API, server-side multi-turn.

Turn 1 sends the original photo + step 1. Every later turn sends only the step's instruction plus
previous_interaction_id; Google keeps the original and all prior outputs in its own stored state.

  GEMINI_API_KEY=... python scripts/run_nanobanana_multiturn.py [benchmark] [run_dir] [--files] [--resolution low|medium|high|ultra_high]

  --files        upload the original once through the Files API and reference it by uri instead of inline base64
  --resolution   input image resolution hint on the turn-1 image part (default: API default)
  --png          upload the original as a losslessly re-encoded PNG (decoded pixels of original.jpg) instead of the JPEG bytes
  --generate     turn 0 asks the model to generate the starting photo itself (nothing is uploaded); the
                 generated image is written to <benchmark>/original.jpg, so point <benchmark> at a copy of
                 the benchmark folder whose steps.json / rois.json you want to reuse.
"""
import base64, datetime, json, os, sys, time
from google import genai

MODEL = "gemini-nano-banana-2.1"
RETRIES = 5

args = [a for a in sys.argv[1:] if not a.startswith("--")]
bench = args[0] if args else "benchmarks/milk"
run = args[1] if len(args) > 1 else "results/milk/nano-banana-2.1-multiturn"
use_files = "--files" in sys.argv
resolution = sys.argv[sys.argv.index("--resolution") + 1] if "--resolution" in sys.argv else None
generate = "--generate" in sys.argv
use_png = "--png" in sys.argv

GEN_PROMPT = ("Candid flash snapshot, 2:3 portrait, two young women against a plain off-white wall that fills the "
    "entire background. The upper right quarter of the frame and the gap between the two women are bare empty wall. "
    "Left: a standing woman with long messy dark brown hair with blonde highlights and bangs, looking down, wearing a "
    "white cropped tank top printed with black text 'DUDES = HOT' and white sweat shorts printed with black text "
    "'I DON'T CARE' and 'Praying'. She has two small black outline star tattoos on her hip, a small silver belly button "
    "piercing, a fine-line tattoo on her outstretched forearm, a thin silver chain bracelet on her wrist, and her right "
    "arm reaches across to hold the seated woman's hair. Her left hand holds a large clear plastic bottle of white milk "
    "to the seated woman's mouth. Right, lower: a seated woman with dark brown hair pulled back, face tilted up drinking "
    "from the bottle with eyes rolled up, silver ear piercings and a dangling silver chain earring, wearing a white "
    "ribbed zip-up jacket with silver text 'MAIN CHARACTER'. Direct on-camera flash, slight shadow on the wall, "
    "amateur phone photo look.")
os.makedirs(run, exist_ok=True)
steps = json.load(open(os.path.join(bench, "steps.json")))
client = genai.Client()
orig_path = os.path.join(bench, "original.jpg")
orig_mime = "image/jpeg"
if use_png:
    from PIL import Image
    png_path = os.path.join(bench, "original.png")
    Image.open(orig_path).convert("RGB").save(png_path, optimize=True)
    orig_path, orig_mime = png_path, "image/png"
if generate:
    orig_part = None
elif use_files:
    f = client.files.upload(file=orig_path); print("uploaded", f.uri)
    orig_part = {"type": "image", "uri": f.uri, "mime_type": orig_mime}
else:
    orig_part = {"type": "image", "data": base64.b64encode(open(orig_path, "rb").read()).decode(), "mime_type": orig_mime}
if resolution:
    orig_part["resolution"] = resolution
prev, blocked, ids = None, [], {}
if generate:
    r = client.interactions.create(model=MODEL, store=True, response_modalities=["image"],
                                   response_format={"type": "image", "aspect_ratio": "2:3", "image_size": "1K"}, input=GEN_PROMPT)
    open(orig_path, "wb").write(base64.b64decode(r.output_image.data)); prev = r.id; ids[0] = r.id
    print("generated original", r.id)

for s in steps:
    n, prompt = s["step"], s["instruction"]
    inp = [orig_part, {"type": "text", "text": prompt}] if n == 1 and not generate else prompt
    out = None
    for attempt in range(RETRIES):
        try:
            r = client.interactions.create(model=MODEL, store=True, response_modalities=["image"],
                                           previous_interaction_id=prev, input=inp)
            out = r.output_image
        except Exception as e:  # rate limit / server error
            print(f"step {n:02d} attempt {attempt + 1}: {e}", file=sys.stderr); time.sleep(5); continue
        if out and out.data:
            prev = r.id; ids[n] = r.id
            break
        print(f"step {n:02d} attempt {attempt + 1}: no image (refused?) status={r.status}", file=sys.stderr)
        out = None
    if out:
        ext = "png" if out.mime_type == "image/png" else "jpg"
        open(os.path.join(run, f"step{n:02d}.{ext}"), "wb").write(base64.b64decode(out.data)); print(f"step {n:02d} ok")
    else:
        blocked.append(n); print(f"step {n:02d} BLOCKED")
        # ponytail: a refused turn is not chained; the next step continues from the last accepted interaction.

if blocked:
    json.dump(blocked, open(os.path.join(run, "blocked.json"), "w"))
variant = (" files" if use_files else "") + (" png" if use_png else "") + (f" {resolution}" if resolution else "") + (" generated" if generate else "")
json.dump({"name": f"Nano Banana 2.1 (multi-turn{variant})", "vendor": "Google", "method": "plain instruction, multi-turn",
           "endpoint": f"google-genai SDK, interactions.create({MODEL}, previous_interaction_id=...)",
           "params": {"response_modalities": ["image"], "store": True, "files_api": use_files, "input_mime": orig_mime, "input_resolution": resolution, "generated_original": generate},
           "date": datetime.date.today().isoformat(), "interaction_ids": ids,
           "notes": "One server-side conversation for all 40 edits; "
                    + ("the model generated the original itself as turn 0, nothing was uploaded. " if generate else "only the original image was uploaded. ")
                    + "Each turn chains on the previous interaction id. Outputs saved exactly as returned by the API."},
          open(os.path.join(run, "meta.json"), "w"), indent=1)
