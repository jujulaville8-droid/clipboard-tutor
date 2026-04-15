import subprocess
import time
import os
import sys
from datetime import datetime

# no external API key needed - uses Claude Code subscription

POLL_INTERVAL = 1.0
MAX_QUESTION_LEN = 500
HEARTBEAT_INTERVAL = 30  # seconds
DEMO_MODE = "--demo" in sys.argv
READINGS_DIR = os.path.expanduser("~/clipboard-tutor/readings")

SYSTEM_PROMPT = (
    "You are a study helper. "
    "If the question has multiple choice options (A, B, C, D, etc.), respond with ONLY the correct letter. Nothing else. "
    "For all other questions, give a concise, accurate answer in 2-4 sentences. "
    "Lead with the answer directly. No disclaimers or preamble."
)


def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_clipboard():
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout


def set_clipboard(text):
    subprocess.run(["pbcopy"], input=text, text=True)


def notify(answer):
    label = answer.strip()
    # only show the toast for single-letter MCQ answers
    if len(label) != 1:
        return
    win_w, win_h, font_size, duration = 26, 18, 11, 1.5
    script = f'''
use framework "AppKit"
use scripting additions

set theRect to current application's NSMakeRect(10, 10, {win_w}, {win_h})
set theWindow to current application's NSWindow's alloc()'s initWithContentRect:theRect styleMask:0 backing:2 defer:false
theWindow's setBackgroundColor:(current application's NSColor's blackColor)
theWindow's setOpaque:false
theWindow's setLevel:1000
theWindow's setIgnoresMouseEvents:true

set theText to current application's NSTextField's labelWithString:"{label}"
theText's setFont:(current application's NSFont's boldSystemFontOfSize:{font_size})
theText's setTextColor:(current application's NSColor's whiteColor)
theText's setAlignment:(current application's NSTextAlignmentCenter)
theText's setBackgroundColor:(current application's NSColor's clearColor)
theText's setBordered:false
theText's setFrame:(current application's NSMakeRect(2, 2, {win_w - 4}, {win_h - 2}))
theWindow's contentView()'s addSubview:theText

theWindow's orderFrontRegardless()
delay {duration}
theWindow's orderOut:missing value
'''
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_question(text):
    stripped = text.strip()
    if not stripped or len(stripped) < 3:
        return None
    return stripped


def ask_claude(client, question):
    if len(question) > MAX_QUESTION_LEN:
        question = question[:MAX_QUESTION_LEN]
        log(f"  (question truncated to {MAX_QUESTION_LEN} chars)")

    if DEMO_MODE:
        time.sleep(0.5)
        return f"[DEMO] Answer to: {question}"

    prompt = SYSTEM_PROMPT + "\n\n" + question
    log("Calling claude...")
    escaped = prompt.replace("'", "'\\''")
    cmd = f"claude -p '{escaped}' --add-dir '{READINGS_DIR}' --allowed-tools 'Read'"
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=60, shell=True,
        executable="/bin/zsh"
    )
    log(f"claude returned: code={result.returncode} stdout={repr(result.stdout[:100])} stderr={repr(result.stderr[:100])}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Unknown error")
    return result.stdout.strip()


def main():
    # unset any stale API key so claude uses its own auth
    os.environ.pop("ANTHROPIC_API_KEY", None)

    client = None
    if DEMO_MODE:
        log("Running in DEMO mode (no API calls)")
    else:
        result = subprocess.run(["which", "claude"], capture_output=True)
        if result.returncode != 0:
            print("Error: 'claude' CLI not found. Make sure Claude Code is installed.")
            sys.exit(1)

    # count readings
    pdf_count = len([f for f in os.listdir(READINGS_DIR) if f.endswith(".pdf")]) if os.path.isdir(READINGS_DIR) else 0

    log("Clipboard Tutor running.")
    log(f"Readings folder: {READINGS_DIR} ({pdf_count} PDFs loaded)")
    log("Copy any question to get an answer.")
    log("Watching clipboard... (Ctrl+C to stop)")
    print()

    last_content = get_clipboard()
    log(f"Initial clipboard: {repr(last_content[:80])}")
    last_heartbeat = time.time()

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            current = get_clipboard()
            if current != last_content:
                log(f"Clipboard changed: {repr(current[:80])}")
                last_content = current
                if not current:
                    log("Empty clipboard, skipping.")
                    continue
                question = extract_question(current)
                if question:
                    display = question[:80] + ("..." if len(question) > 80 else "")
                    log(f'Question: "{display}"')

                    try:
                        answer = ask_claude(client, question)
                        set_clipboard(answer)
                        last_content = answer
                        log(f"Answer ready ({len(answer)} chars) - on your clipboard!")
                        log(f"Answer: {answer}")
                        notify(answer)
                    except Exception as e:
                        log(f"API error: {e}")
                        log("Clipboard unchanged. Continuing...")

            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                print(".", end="", flush=True)
                last_heartbeat = now

    except KeyboardInterrupt:
        print()
        log("Stopped.")


if __name__ == "__main__":
    main()
