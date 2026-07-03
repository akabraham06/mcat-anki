/* Copyright: Ankitects Pty Ltd and contributors
 * License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */

/* eslint
@typescript-eslint/no-unused-vars: "off",
*/

let time: number; // set in python code
let timerStopped = false;

let maxTime = 0;
// MCAT exam cards render a per-question countdown (maxTime - elapsed) as a thin
// section-coloured calibration bar; normal cards keep the classic count-up.
let countdown = false;
let timedOut = false;
// Section hue for the MCAT exam calibration bar (empty for normal cards).
let barColor = "";

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
        const frac = Math.max(0, Math.min(1, remaining / maxTime));
        // A thin calibration bar in the section hue that depletes as the budget
        // runs down; the last 20% reads as "low" (warn), not a jarring alarm.
        const low = frac <= 0.2;
        const fill = barColor || "#4e8cff";
        timeNode.innerHTML =
            `<span class="mcat-timer${low ? " low" : ""}">`
            + `<span class="mcat-timer-time">${fmt(remaining)}</span>`
            + `<span class="mcat-timer-track">`
            + `<span class="mcat-timer-fill" style="width:${frac * 100}%;background:${fill}"></span>`
            + `</span></span>`;
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

function showQuestion(
    txt: string,
    maxTime_: number,
    countdown_ = false,
    barColor_ = "",
): void {
    showAnswer(txt);
    time = 0;
    maxTime = maxTime_;
    countdown = countdown_;
    barColor = barColor_;
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
