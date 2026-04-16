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
    "You are helping a university student study. "
    "Answer from your general knowledge directly — do not try to read any files. "
    "If the question has multiple choice options (A, B, C, D, etc.), respond with ONLY the correct letter(s). Nothing else. "
    "If there is more than one correct answer, return the letters separated by commas (e.g. 'A, C') — no more than 5 characters total. "
    "For all other questions, answer in 2-4 sentences as if you're a student writing a quick note to yourself. "
    "Write like a real person, not an AI: "
    "use plain, everyday language; contractions are fine; vary sentence length naturally; "
    "do not use em dashes (—), semicolons, or bullet points; "
    "do not hedge with phrases like 'it's worth noting', 'essentially', 'fundamentally', 'in essence', 'ultimately', or 'at its core'; "
    "do not start with 'The answer is' or restate the question; "
    "skip transitional words like 'moreover', 'furthermore', 'however' at the start of sentences; "
    "avoid tricolons (lists of three) and overly balanced/polished phrasing; "
    "just state the point directly, the way a smart student would jot it down. "
    "Never use direct quotations from the readings — always paraphrase in your own words. "
    "No preamble, no disclaimers, no meta-commentary."
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
    # strip trailing punctuation
    raw = answer.strip().rstrip(".").upper()
    import re
    # case 1: compact form like "ABD" or "AC" — all letters, no separators, short
    if re.fullmatch(r"[A-Z]{1,6}", raw):
        letters = list(raw)
    else:
        # case 2: separated form like "A, C", "A AND C", "A & C"
        letters = re.findall(r"(?<![A-Z])[A-Z](?![A-Z])", raw)
    if not letters or len(letters) > 6:
        log(f"toast skipped: parsed letters={letters} from answer={repr(answer[:60])}")
        return
    label = ", ".join(letters)
    log(f"toast firing: {label}")
    # dynamic width based on character count (rough: ~9px per char + padding)
    char_count = len(label)
    win_w = max(26, 10 + char_count * 9)
    win_h, font_size, duration = 18, 11, 2.0
    # Use a PyObjC-based approach via python so window can appear over fullscreen apps.
    # Falls back silently if pyobjc not available.
    py_script = f'''
from AppKit import (
    NSApplication, NSWindow, NSColor, NSTextField, NSFont, NSScreen,
    NSMakeRect, NSApplicationActivationPolicyAccessory,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSTextAlignmentCenter,
)
from Foundation import NSRunLoop, NSDate

app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

# Position in bottom-left of the visible frame (excludes Dock and menu bar)
screen = NSScreen.mainScreen()
visible = screen.visibleFrame()
x = visible.origin.x + 12
y = visible.origin.y + 12
rect = NSMakeRect(x, y, {win_w}, {win_h})
win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(rect, 0, 2, False)
win.setBackgroundColor_(NSColor.blackColor())
win.setOpaque_(False)
win.setLevel_(1000)
win.setIgnoresMouseEvents_(True)
win.setCollectionBehavior_(
    NSWindowCollectionBehaviorCanJoinAllSpaces
    | NSWindowCollectionBehaviorFullScreenAuxiliary
    | NSWindowCollectionBehaviorStationary
    | NSWindowCollectionBehaviorIgnoresCycle
)

label = NSTextField.labelWithString_("{label}")
label.setFont_(NSFont.boldSystemFontOfSize_({font_size}))
label.setTextColor_(NSColor.whiteColor())
label.setAlignment_(NSTextAlignmentCenter)
label.setBackgroundColor_(NSColor.clearColor())
label.setBordered_(False)
label.setFrame_(NSMakeRect(2, 2, {win_w - 4}, {win_h - 2}))
win.contentView().addSubview_(label)

win.makeKeyAndOrderFront_(None)
win.orderFrontRegardless()

# Pump the run loop until duration expires, so the window actually stays visible.
end = NSDate.dateWithTimeIntervalSinceNow_({duration})
NSRunLoop.currentRunLoop().runUntilDate_(end)
win.orderOut_(None)
'''
    proc = subprocess.Popen(
        [sys.executable, "-c", py_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Give it a moment to fail fast; don't block on the full duration.
    try:
        _, err = proc.communicate(timeout=0.3)
        if proc.returncode != 0 and err:
            log(f"toast error: {err.decode(errors='replace').strip()[:200]}")
    except subprocess.TimeoutExpired:
        pass  # still running, that's fine


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
    cmd = f"claude -p '{escaped}' --allowed-tools ''"
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=180, shell=True,
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

    # verify the toast can work (needs pyobjc)
    try:
        import AppKit  # noqa: F401
        log("AppKit available — fullscreen toast enabled.")
    except ImportError:
        log(f"WARNING: AppKit not available in {sys.executable}")
        log("  Toast will not show. Install with:")
        log(f"  {sys.executable} -m pip install pyobjc-framework-Cocoa")

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
