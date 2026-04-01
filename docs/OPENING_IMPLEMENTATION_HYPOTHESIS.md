# Opening Implementation Hypothesis

## Current Hypothesis

The strongest version of AOG is not a new video generator.
It is a reliable bridge from a good SVI-rendered opening video into matching generated music and optional effects.

## Working Assumptions

1. `svi.pro_workflow_mmmmn.json` remains the authoritative video workflow.
1a. `audio_ace_step_1_5_split_4b.json` is the authoritative ACE-Step reference workflow.
1b. `mmaudio_test.json` is the authoritative MMAudio reference workflow.
2. AOG should only operate after the video already exists.
3. MMAudio should not be reduced to summary text only when it is enabled.
4. MMAudio outputs should be split into:
   - latent and embedding features for generation conditioning
   - authoring features for human and LLM writing support:
     - summary
     - structured timeline
     - semantic scene cues
5. QwenVL should be introduced as the primary video-semantic-analysis layer for authoring.
   It should consume video frames or frame sequences directly.
   It does not require MMAudio feature extraction to run.
   It does not need raw MMAudio latent tensors as input.
   The preferred merged authoring contract is:
   - QwenVL scene analysis
   - optional MMAudio-derived summary
   - optional MMAudio-derived structured timeline
   - optional MMAudio-derived latent structure cues
5. Highest-tier target:
   ACE-Step-adjacent music generation should be informed by both:
   - text inputs
   - video-derived analysis signals
   Current implementation may begin with text and metadata that are authored from those signals before full direct conditioning parity exists.
   Therefore the most important practical path is:
   - use MMAudio-derived latent structure to help a real LLM write better ACE-Step prompts and lyrics
   - not simplistic heuristic rewriting
6. Prompt and lyric generation should support both:
   - human-authored mode
   - LLM-authored mode
   No heuristic, fallback, or rule-based drafting path is acceptable.
   Current practical implementation:
   use `ComfyUI-QwenVL` with `Qwen3-VL-4B-Instruct` for video-aware prompt and lyric authoring.
   Keep `qwen_4b_ace15.safetensors` on the ACE-Step conditioning side.
7. Prompt and lyric generation should support an explicit shared authoring language.
   Default policy:
   - `authoring_language == ace_language`
   Language mismatch should only exist as an advanced override.
8. Lyric generation should support explicit language selection.
9. Optional effect generation should be available from the same video-derived features.

## Pipeline

1. Render the opening clip in the external SVI workflow.
2. Load the rendered video into AOG.
3. Optionally extract MMAudio video features.
4. Split those outputs into:
   - conditioning-facing analysis summaries for music and SFX
   - authoring package for prompt and lyric drafting:
     - summary
     - structured timeline
     - semantic scene cues
5. Run QwenVL video analysis over the same clip to produce the primary semantic authoring context.
6. Resolve prompt and lyric inputs with either:
   - human-written text
   - LLM-written text from:
     - QwenVL scene analysis
     - summary
     - structured timeline
     - semantic scene cues
     - latent-derived structure cues
   Note:
   LLM authoring inputs are not raw latents.
   QwenVL receives the video directly, not MMAudio latent tensors.
   The authoring contract is built by merging QwenVL scene analysis with optional MMAudio-derived timing and structure cues.
   This authoring layer is the main realistic route for improving synchronization quality before direct latent conditioning exists.
   Current model choice:
   use `Qwen3-VL-4B-Instruct` through `ComfyUI-QwenVL` for authoring.
   Do not treat the ACE-Step text encoder checkpoint itself as the free-form authoring runtime.
7. Resolve language-facing settings:
   - `authoring_language`
   - `lyrics_language`
   - `ace_language`
   Default policy:
   - `authoring_language == lyrics_language == ace_language`
8. Generate the music track with ACE-Step using text and metadata informed by the video analysis package.
   Current runtime contracts should keep summaries and cues, not raw latent tensors.
9. Optionally generate effect stems as a target-tier branch.
10. Mux the final audio back into the rendered video.

## Workflow UI Constraints

- Canvas example workflows must be usable with video upload alone.
- Manual path entry is not acceptable for the upload-first workflow path.
- `title` and `theme` are not required UI inputs for prompt or lyric drafting.
- Saved workflow widget order must remain stable after reload.
- For that reason, runtime inputs should avoid the literal field name `seed` in user-facing custom nodes when saved workflow restoration is important.
  - preferred names:
    - `music_seed`
    - `sfx_seed`

## Required Options

### Option 1

- human prompt
- human lyrics
- selected lyric language
- optional MMAudio latent and embedding analysis outputs may still influence music generation planning, even if the implementation path reaches ACE-Step through authored text and metadata

### Option 2

- LLM prompt
- LLM lyrics
- selected lyric language
- drafting based on:
  - summary
  - structured timeline
  - semantic scene cues
  - latent-derived structure cues
- optional MMAudio latent and embedding analysis outputs may still influence music generation planning, even if the implementation path reaches ACE-Step through authored text and metadata

### Option 3

- all of option 1 or option 2
- plus MMAudio-guided effect generation as an optional target-tier branch

## Success Criteria

- The video quality is inherited from the verified SVI workflow.
- The generated track follows clip pacing and intensity better than a prompt-only baseline.
- The generated track follows clip pacing and intensity better because prompt and lyrics are authored from latent-derived structure cues, not only plain summary text.
- Prompt and lyric authoring are not locked to one workflow.
- The synchronization core comes from video analysis signals, not only summary text.
- LLM authoring quality comes from summary plus timeline plus semantic cues, not summary alone.
- LLM authoring also incorporates latent-derived structure cues rather than raw latent tensors.
- Lyrics can be generated in an explicitly selected language instead of being fixed to one default.
- The final deliverable is a single playable video file with generated music and optional effects.

## Current Review Result

- `qwenvl_full_loop1`, `qwenvl_full_loop2`, and `qwenvl_full_loop3` are passing end-to-end validations.
- It confirms:
  - no meaningful truncation of the source clip
  - successful final mux into a playable output video
  - QwenVL-authored prompt generation from video analysis and merged MMAudio context
  - QwenVL-authored lyrics from video analysis and merged MMAudio context
  - full target-tier SFX output on the same run
- `authoring_context.json` is now a required trace artifact for proving that prompt and lyric authoring consumed video-derived context.

## Current Loop 3 Conclusion

- Non-intentional truncation is no longer the primary blocker.
- The remaining highest-tier blockers are:
  - stronger generation-facing conditioning than text/meta augmentation alone
  - higher-quality prompt and lyric refinement
  - reducing repeated QwenVL model reload cost

## Required Preconditions For A Real Full-Length Validation

The following must be true before a full-length validation is meaningful:

1. The entire input video duration must be processed by MMAudio without silent truncation or hidden shortening.
2. The feature contract must cover the full clip and preserve:
   - summary
   - structured timeline
   - semantic scene cues
   - latent-derived structure cues
3. Prompt generation must use a real LLM runtime, not a heuristic substitute.
4. Lyric generation must use the same real LLM runtime and target the requested output language.
5. The ACE-Step input package must be produced from those authored results, not from manual guesswork.
6. Optional SFX must be generated from the same full-length clip analysis.
7. The final mux must be reviewed by listening and watching the full render, not only by checking file creation.

## Verification Checklist

- verify that the extracted duration matches the intended source duration
- verify that the timeline covers the entire clip
- verify that the prompt references the actual visual arc
- verify that the lyrics match the same arc and chosen language
- verify that the SFX stem supports rather than masks the music
- verify that the final combined video feels synchronized by human review

## Removed Ideas

- voice conversion
- vocal stem splitting
- instrumental recombination
## Review Loop Status

- Review loop 1:
  - replaced the broken local authoring path with `ComfyUI-QwenVL`
  - verified full-duration mux and SFX generation on the same run
  - confirmed that video-derived context is persisted through `authoring_context.json`
- Review loop 2:
  - strengthened the authoring contract so video evidence overrides abstract theme wording
  - revalidated full-duration output and final mux
  - rechecked prompt and lyric generation from video-aware context
- Review loop 3:
  - finalized phase ordering as `QwenVL authoring -> ACE-Step -> MMAudio SFX -> mux`
  - verified final artifacts preserve full input duration
  - verified video-derived cues are auditable through request/response artifacts

- Review loop 4:
  - diagnosed and corrected six bugs in `run_aog_audio_pipeline.py` where node method calls were missing the `enabled` argument and passing nonexistent keyword arguments (`llm_model`, `title`, `theme`) to draft nodes
  - corrected `qwenvl_bundle` input slot index from 7 to 8 in `AOGLyricsDraft` across all three workflow JSON files
  - diagnosed and corrected a disconnected-input bug in `AOG_Full_Music_SFX_Mux.json` where `AOG SFX Stage Gate` received stale link references for `pipeline_toggles` and `mmaudio_featureutils`; both inputs were effectively unconnected at runtime

## Present Outcome

- Full-duration video/audio preservation: verified
- Final video combine: verified
- `video-derived cues -> prompt/lyrics generation`: verified at the artifact and request level
- `video-derived cues -> ACE-Step direct latent conditioning`: not implemented yet
- `LLM prompt quality`: usable baseline
- `LLM lyrics quality`: still requires further work before calling it production-ready
