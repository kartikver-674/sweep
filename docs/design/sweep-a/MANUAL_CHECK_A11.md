# A11 manual browser check (owner, ~15–20 min)

The automated checks ran on Chromium. This is the real-browser pass: **desktop Safari, Firefox, and an iPhone**, plus
**dark mode** and **reduced motion** on one of them. Everything below uses made-up data from the test harness — no real
résumé, no real key, nothing is searched or charged.

## Start the site (one terminal, leave it running)

```sh
cd ~/ReactNative/job-scraper
env $(grep -oE '^[A-Z][A-Z0-9_]*=' .env | tr '\n' ' ') HTTP_PROXY= HTTPS_PROXY= \
  D7B_PORT=5277 .venv/bin/python docs/design/sweep-a/harness/states-app.py
```

Wait for `READY 5277` (its own port: 5077 is the automated harnesses' default, so the two never collide). Each link below sets up one situation and opens its page (it replaces your session — open them in
order, or in separate private windows). Stop the server with Ctrl+C when done.

**iPhone:** the server listens on 127.0.0.1 only, so a physical phone cannot reach it. Use the iOS Simulator (Xcode →
Open Developer Tool → Simulator, then Safari inside it — it reaches 127.0.0.1), or check the phone on a staging deploy.

**Dark mode:** the sun/moon switch in the header (or your system setting). **Reduced motion:** macOS System Settings →
Accessibility → Display → Reduce motion (iPhone: Settings → Accessibility → Motion → Reduce Motion).

## The happy path

| # | Open | Try | Looks right when |
|---|---|---|---|
| 1 | [Upload](http://127.0.0.1:5277/__go/fresh?to=/) | Drag across the job cards on the desk; press "Sweep it for me", then "Start over"; open the three peeks | Strong cards fly to the shortlist, weak ones fade; nothing clipped; peeks open and close |
| 2 | [Review](http://127.0.0.1:5277/__go/all_ready?to=/review) | Tap a skill chip, change its weight, Remove one; open the experience chip; "+ Add a skill" | One panel opens at a time; the dots follow the weight |
| 3 | [Search coverage](http://127.0.0.1:5277/__go/reviewed3?to=/key) | Pick Deep Sweep; "Set up Deep Sweep"; step through 1 → 3 and back; "Back to the options" | The three boards pop onto the outer ring (and slowly orbit); one step shows at a time |
| 4 | [Configure](http://127.0.0.1:5277/__go/paid?to=/configure) | Switch LinkedIn off and on; change "Which jobs"; open "How is this worked out?" | The price dims, then the figure and the jar's fill change together; stripes stay inside the jar |
| 5 | [Configure near the line](http://127.0.0.1:5277/__go/edge?to=/configure) | Advanced → "Jobs per search" +, once or twice | The jar goes red-striped and wobbles once when it tips over; the sentence under the price says why |
| 6 | [Confirm](http://127.0.0.1:5277/__go/c_paid_one?to=/confirm) | Open "How is this worked out?" | One ticket: summary left, peach stub right with notches; on a phone, stacked |
| 7 | [Confirm, partly covered](http://127.0.0.1:5277/__go/c_over_one?to=/confirm) | Tick "Run with my available credit anyway" | The button is a dashed "not yet" until ticked, then a normal button |
| 8 | [Progress, Deep](http://127.0.0.1:5277/__go/p_paid_one_some?to=/running) | Tap a listing under Latest matches; open the Searches peek | The brush sits on the end of the bar; "Now: Board · City"; a listing opens to its skills |
| 9 | [Progress, Quick](http://127.0.0.1:5277/__go/p_free_one_working?to=/running) | Watch the bar | The brush rides the moving stripe; the four passes are marked |
| 10 | [Results, three résumés](http://127.0.0.1:5277/__go/m_all?to=/results) | Open "Why it matched" (click inside its chips); click a card's empty area; switch résumé tabs; Filter and sort; Export… | Clicking inside the open peek does NOT open the job; clicking the card does (new tab); "Top of the pile" on the first card |
| 11 | [Results, one résumé](http://127.0.0.1:5277/__go/s1_19?to=/results) | Open "How match scores work" | The zero-line picture; cards with full-width Apply on a phone |
| 12 | [A missing page](http://127.0.0.1:5277/__go/fresh?to=/no-such-page) | — | "This page isn't here." with a way back |
| 13 | Any page | The Feedback button in the header | A sticker dialog; Esc or Close shuts it |

## What to tell me

For anything that looks off, the row number, the browser, light/dark, and what you saw (a screenshot helps): clipped or
overlapping text, something that jumps or flickers, unreadable text, a page you can scroll sideways on a phone, motion that
still happens with Reduce Motion on, or a difference between Safari, Firefox and Chrome. "All fine" is a fine answer.
