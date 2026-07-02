/* Copyright: Ankitects Pty Ltd and contributors
 * License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */

/* eslint
@typescript-eslint/no-unused-vars: "off",
*/

let time: number; // set in python code
let timerStopped = false;

let maxTime = 0;
// MCAT exam cards render a per-question countdown (maxTime - elapsed) with
// green -> amber -> red thresholds; normal cards keep the classic count-up.
let countdown = false;
let timedOut = false;

function fmt(secs: number): string {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
}

function updateTime(): void {
    const timeNode = document.getElementById("time");
    if (maxTime === 0) {
        timeNode.textContent = "";
        return;
    }

    if (countdown) {
        const remaining = Math.max(0, maxTime - time);
        const frac = remaining / maxTime;
        let color: string;
        if (frac > 0.5) {
            color = "#2e9e44"; // green
        } else if (frac > 0.2) {
            color = "#e0a100"; // amber
        } else {
            color = "red";
        }
        timeNode.innerHTML = `<font color="${color}">${fmt(remaining)}</font>`;
        if (remaining <= 0 && !timedOut) {
            timedOut = true;
            timerStopped = true;
            // Ask the reviewer to auto-reveal the answer and move on.
            try {
                pycmd("mcat_timeout");
            } catch (e) {
                // bridge not ready; ignore
            }
        }
        return;
    }

    time = Math.min(maxTime, time);
    if (maxTime === time) {
        timeNode.innerHTML = `<font color=red>${fmt(time)}</font>`;
    } else {
        timeNode.textContent = fmt(time);
    }
}

let intervalId: number | undefined;

function showQuestion(txt: string, maxTime_: number, countdown_ = false): void {
    showAnswer(txt);
    time = 0;
    maxTime = maxTime_;
    countdown = countdown_;
    timedOut = false;
    updateTime();

    if (intervalId !== undefined) {
        clearInterval(intervalId);
    }

    intervalId = setInterval(function() {
        if (!timerStopped) {
            time += 1;
            updateTime();
        }
    }, 1000);
}

// Freeze the countdown once an MCAT exam option is selected, so revealing the
// explanation and pressing Next is not rushed by the timeout.
function mcatFreeze(): void {
    timerStopped = true;
}

function showAnswer(txt: string, stopTimer = false): void {
    document.getElementById("middle").innerHTML = txt;
    timerStopped = stopTimer;
}

function selectedAnswerButton(): string {
    const node = document.activeElement as HTMLElement;
    if (!node) {
        return;
    }
    return node.dataset.ease;
}
