# Clipboard Tutor

Watches your macOS clipboard. When you copy a question, it sends it to Claude Code,
puts the answer back on your clipboard, and (for single-letter MCQ answers) flashes
a tiny black box in the bottom-left corner of the screen.

## Run it

```
python3 ~/clipboard-tutor/study.py
```

Demo mode (no API calls):

```
python3 ~/clipboard-tutor/study.py --demo
```

Stop with **Ctrl+C**. Restart by pressing the **up arrow** then **Enter**.

## Requirements

- macOS (uses `pbpaste` / `pbcopy` / `osascript`)
- The `claude` CLI on your PATH (check with `which claude`)
- Python 3

## How it works

- Polls the clipboard every 1s
- On change, sends the text to `claude -p` with a study-helper system prompt
- For multiple-choice questions Claude returns just the letter (A/B/C/D)
- For other questions Claude returns 2–4 sentences
- Answer is copied to the clipboard automatically
- Single-letter answers also pop a small toast in the bottom-left for 1.5s
- Sentence answers are silent — just check your clipboard

## Readings

Drop PDFs into `~/clipboard-tutor/readings/` and Claude will be able to read them
when answering (the script grants `--add-dir` + `Read` tool access to that folder).

## Files

- `study.py` — main script
- `readings/` — optional PDFs Claude can reference
- `requirements.txt` — legacy, not needed for current script
