import os
import subprocess
import time

import pyautogui

from jarvis.brain.macro_store import MacroStep, get_macro_store

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _execute_step(step: MacroStep) -> str:
    p = step.params
    action = step.action

    if action == "type":
        pyautogui.write(p.get("text", ""), interval=0.03)

    elif action == "hotkey":
        keys = p.get("keys", [])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]
        pyautogui.hotkey(*keys)

    elif action == "press":
        pyautogui.press(p.get("key", "enter"))

    elif action == "click":
        x, y = p.get("x"), p.get("y")
        if x is not None and y is not None:
            pyautogui.click(int(x), int(y))
        else:
            pyautogui.click()

    elif action == "double_click":
        x, y = p.get("x"), p.get("y")
        if x is not None and y is not None:
            pyautogui.doubleClick(int(x), int(y))
        else:
            pyautogui.doubleClick()

    elif action == "right_click":
        x, y = p.get("x"), p.get("y")
        if x is not None and y is not None:
            pyautogui.rightClick(int(x), int(y))
        else:
            pyautogui.rightClick()

    elif action == "move":
        pyautogui.moveTo(int(p.get("x", 0)), int(p.get("y", 0)), duration=0.3)

    elif action == "scroll":
        clicks = int(p.get("clicks", 3))
        x, y = p.get("x"), p.get("y")
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=int(x), y=int(y))
        else:
            pyautogui.scroll(clicks)

    elif action == "wait":
        time.sleep(float(p.get("seconds", 1.0)))

    elif action == "write_line":
        pyautogui.write(p.get("text", ""), interval=0.03)
        pyautogui.press("enter")

    elif action == "open_app":
        path = p.get("path", "")
        if path:
            os.startfile(path)
            time.sleep(float(p.get("wait", 1.5)))

    elif action == "run_command":
        cmd = p.get("command", "")
        if cmd:
            subprocess.Popen(cmd, shell=True)
            time.sleep(float(p.get("wait", 0.5)))

    elif action == "screenshot_region":
        import datetime as dt
        x, y, w, h = (
            int(p.get("x", 0)),
            int(p.get("y", 0)),
            int(p.get("width", 400)),
            int(p.get("height", 300)),
        )
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(os.path.expanduser("~"), "Pictures", f"jarvis_{stamp}.png")
        img = pyautogui.screenshot(region=(x, y, w, h))
        img.save(out)

    else:
        return f"Unknown action: {action}"

    return "ok"


def run_macro(macro_id: str, delay_before: float = 2.0) -> tuple[bool, str]:
    store = get_macro_store()
    macro = store.get(macro_id)
    if not macro:
        return False, f"Macro '{macro_id}' not found."

    if delay_before > 0:
        time.sleep(delay_before)

    try:
        for i, step in enumerate(macro.steps):
            result = _execute_step(step)
            if result != "ok":
                return False, f"Step {i + 1} ({step.action}) failed: {result}"
        store.record_run(macro_id)
        return True, f"Macro '{macro.name}' completed ({len(macro.steps)} steps)."
    except pyautogui.FailSafeException:
        return False, "Macro aborted: mouse moved to corner (failsafe)."
    except Exception as exc:
        return False, f"Macro error: {exc}"
