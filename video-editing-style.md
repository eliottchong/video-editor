---
name: video-editing-style
description: >
  Analyze reference footage and produce actionable video-editing style guides.
  Use when the user shares an MP4 and asks for editing direction or a generative
  video prompt that matches the reference style.
---

# Video Editing Style Skill

Reverse-engineer the editing language of a reference video and turn it into a
reusable style guide or a single Veo-ready generation prompt.

When the user wants a new video, end your response with one paragraph labeled
`VEO PROMPT:` that a text-to-video model can use directly. Fold in pacing,
camera, color, audio, and mood cues from the reference clip.

## Output template

```text
## Style in one sentence
...

## Replication checklist
1. ...

VEO PROMPT:
<single paragraph, present tense, cinematic detail>
```
