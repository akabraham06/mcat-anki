### MCAT Anki Mastery: strings for the "beat-your-ghost" timed-session mode,
### where the user races their previous best exam session.

## Ghost label and live readout shown in the reviewer.

# Prefix of the ghost label, e.g. "Your best: 82% · 11:20 · Jun 30".
mcat-ghost-your-best = Your best
# Prefix of the live comparison, e.g. "vs best: +6s ahead · 1 correct behind".
mcat-ghost-vs-best = vs best
mcat-ghost-seconds-ahead = +{ $seconds }s ahead
mcat-ghost-seconds-behind = -{ $seconds }s behind
mcat-ghost-pace-even = on pace
mcat-ghost-correct-ahead =
    { $count ->
        [one] { $count } correct ahead
       *[other] { $count } correct ahead
    }
mcat-ghost-correct-behind =
    { $count ->
        [one] { $count } correct behind
       *[other] { $count } correct behind
    }
mcat-ghost-accuracy-even = tied on accuracy

## End-of-session result.

mcat-ghost-new-personal-best = New personal best!
mcat-ghost-you-won = You beat your ghost!
mcat-ghost-ghost-won = Your ghost held on this time.
mcat-ghost-tie = Dead heat with your ghost.
mcat-ghost-baseline-set = Baseline set — race your ghost next time.
