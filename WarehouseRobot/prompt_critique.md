========================================================================
# Perplexity  (:7824, fact-checking, web sources)  [22.4s]
========================================================================
Here is a structured, point-by-point critique of the provided prompt/spec. I quote the exact text sections and explain what is ambiguous, underspecified, or inconsistent, and offer concrete improvement suggestions.

Ambiguities
- Quote: “The bot connects to the tournament server at `localhost:7474`” and “Open a TCP connection to `localhost:7474`.” 
  - Issue: No guidance on how to handle DNS or IPv6 vs IPv4, or if localhost can resolve differently in some environments. Also, what if the port is unavailable? The spec later covers timeouts, but not connection failures. 
  - Improvement: Add explicit behavior for connection failure (retry policy, backoff, or immediate INVALID reason like connection_error).

- Quote: “The bot's submission is one or more `TRIP` lines followed by a single `END` line.”
  - Issue: It’s unclear whether there is a maximum number of `TRIP` lines per round, though later the server computes trip_count. Ambiguity about whether a single-item trip line is allowed if multiple items exist (it is allowed, but not explicitly stated here beyond “A single-item trip is fine” in §1.3). 
  - Improvement: State any per-round maximum lines or item coverage guarantees beyond “Every item index 0..N−1 must appear in exactly one position.”

- Quote: “The bot must implement a full strategy that produces a complete trip plan for each round.” and “Trip order does not affect the score (each trip starts and ends at (0,0) with load 0), but the order is preserved in the log for replay.”
  - Issue: “Complete trip plan” is vague about optimizations; but more importantly, it implies the bot can be suboptimal. The spec doesn’t forbid silly submissions, but it would help to clarify success criteria: any valid plan is scored; but performance depends on time/mathematics. 
  - Improvement: Clarify acceptable behavior when the computed plan is suboptimal but valid (it should still be scored, with potential INVALID only for rule violations). Also specify any preferred minimal time or scoring goals for tie-breakers.

Underspecified edge cases
- Quote: “Speed(load_kg) = 10 − (load_kg // 10)” and “speed 0 kg → 10 m/min, 1–9 kg → 10 m/min, 10 kg → 9 m/min, …, 90 kg → 1 m/min, 91–99 kg → 1 m/min, ≥ 100 kg → 0 m/min (stuck).”
  - Issue: The description has overlapping ranges (0 kg and 1–9 kg both yield 10) but is mostly clear. However, the exact calculation for speed at every leg uses the load at the leg's start; the rule “pickup at B happens after arrival; load update applies to the next leg” could cause confusion in edge cases where multiple items are at the same location: a zero-distance leg followed by a pickup would affect the next leg if it’s nonzero. 
  - Improvement: Provide a precise, small, concrete example illustrating a trip with two items at the same bin and how loads evolve leg-by-leg.

- Quote: “The drop-off point is at (0, 0). The robot starts every round at (0, 0) with load 0 kg, and at the end of every trip must be at (0, 0) to unload.”
  - Issue: It says “end of every trip” must be at origin to unload, but the actual simulation depends on server. If a trip ends at (0,0) but the last leg was zero distance, does unloading still occur instantly? It’s implied but not explicit.
  - Improvement: State explicitly that unloading occurs immediately upon arriving at (0,0), regardless of prior leg lengths, and that load resets to 0 at that moment.

- Quote: “The server uses the order verbatim and does not reorder.”
  - Issue: This means the server simulates trips in the order sent; but it might be beneficial to clarify what happens if a TRIP line is malformed or contains an invalid index. The spec defines invalidity but not behavior if the first invalid line occurs mid-round.
  - Improvement: Clarify error handling scope: if a later TRIP line is malformed, is the entire round INVALID? (It says first failure determines INVALID, so fine, but restating helps avoid ambiguity.)

Protocol / interface gotchas
- “Lines have no leading or trailing whitespace beyond the single terminating `\n`.”
  - Issue: In practice, some wire-transports or test harnesses might introduce CRLF or stray whitespace. The spec forbids CRLF and whitespace, but implementing code should robustly reject or handle unexpected whitespace. 
  - Improvement: Provide a small tolerance or explicit examples of invalid examples to ensure correct parser behavior.

- “The first failure determines INVALID: The submission did not arrive (no END line within 30s)”
  - Issue: The 30-second budget is wall-clock, not CPU time. If a bot blocks forever, it’s not acceptable. The spec says do not set socket read timeouts, idle reads should block. This creates a practical risk: a bot that accidentally stalls could be penalized. The spec addresses it, but a concrete protocol for partial progress (e.g., partial trips before timeout) could be clearer.
  - Improvement: Include guidance on how to handle partial progress and what constitutes a valid partial submission under timeout, or specify that the server imposes a hard timeout and the bot should exit gracefully.

Inconsistencies
- Load and stuck rule vs. return trip: 
  - The rule: “If at the start of any leg the robot's load is ≥ 100 kg AND the leg has positive distance, the trip is invalid.”
  - But the speed rule says “≥ 100 kg → 0 m/min (stuck)” and a leg with positive distance at start would be invalid, implying the server will treat such a trip as invalid. This is consistent, but the exact boundary for a zero-distance leg could create edge cases: “A zero-distance leg (the next pickup is at the current position because two consecutive items share a bin) is fine at any load.”
  - Inconsistent? Not strictly, but it could use a clarifying example to prevent misinterpretation about when a leg is considered positive distance.

- “Trip order does not affect the score” and “The server logs trips in the order sent.”
  - This is consistent, but could be confusing: a reader might think trip order impacts timing due to cumulative loads. The spec clarifies loads reset per trip, which resolves confusion. No actual inconsistency, but clearer emphasis could help.

Missing information that would help implementers
- Error handling policy outside INVALID: If a bot connects but misbehaves (e.g., sends data after END), what is the expected behavior? The protocol hints at strict line-based parsing, but explicit guidance on stray lines after END would help.
- Timeout handling specifics for per-round: The 30-second budget is stated, but no guidance on what happens if the server hasn’t finished computing or if the bot takes time to send END after ROUND data. It mentions the server replies with OK/INVALID after END; a precise timeline expectation would be helpful.
- Data typing and numeric formats: We know item indices are decimal with no leading zeros; but what about negative numbers in malformed trips? The invalid cases cover negative indices, but not leading plus signs or whitespace around numbers. The malformed_trip_<i> rule mentions leading zero in an index as invalid; are signs allowed? The spec implies only digits, but stating explicitly would reduce ambiguity.
- Constraints around 1–32 character BOTNAME: It’s stated, but no guidance on character set if a user tries to generate an environment variable with disallowed characters; the server will close the connection. It might help to provide a sample allowed value and a recommended validation approach, though the server enforces it.

Concrete example of issues with exact text
- Ambiguity in speed edge cases:
  - Text: “speed(load_kg) = 10 − (load_kg // 10)”
  - Clarification issue: For load_kg in , speed is 10; for 10–19, speed is 9; etc. The text later restates some of that. The exact behavior for load exactly 100 is 0 m/min, but the text says “≥ 100 kg → 0 m/min (stuck)”; this is clear, but the earlier bullet already included a “speed is 0 if load_kg ≥ 100” band. It’s consistent, but could be condensed to avoid confusion.
- Edge case about zero-distance legs:
  - Text: “The pickup at B happens after arrival; the load update applies to the next leg. So picking up a heavy item at the end of a trip slows only the return-to-origin leg, not the leg used to reach that item.”
  - Issue: If item A is at the same bin as item B (zero-distance between them), there is a sequence where the pickup at B could slow the next leg even if you traveled zero distance to reach B from A. The text addresses “zero distance if two consecutive items share a bin” but then the load update applies to the next leg. This needs a concrete example to avoid misinterpretation.
  - Improvement: Add a short explicit example illustrating two consecutive items at the same coordinates and how loads evolve for the next (nonzero) leg.

Recommendations to improve the prompt
- Add a concise glossary and 1–2 concrete examples for tricky mechanics (especially load progression, zero-distance legs, and the stuck rule).
- Explicitly state per-round maximum lines or a maximum total plan size, if any, to bound bot output.
- Clarify behavior on connection or protocol violations beyond the defined INVALID reasons (e.g., if the bot sends extra lines after END, or partial data after 30s).
- Provide a minimal, concrete test snippet or pseudo-example showing a tiny round with 2–3 items to illustrate timing, loads, and leg durations.
- Consider adding a small optional constraint or scoring hint: e.g., whether to optimize total time vs. simplicity, to guide sane implementations without forcing optimal strategies.

Illustrative example (to help resolve a key ambiguity)
- Suppose two items at (1,0) with weights 40 and 60 kg, visited in that order in a single trip, starting from (0,0) with load 0.
  - Leg 1: travel (0,0) -> (1,0) with load 0 → distance 1, speed 10 m/min, time 0.1 min. Arrive, pickup first item (40 kg). Load becomes 40 kg for the next leg.
  - Leg 2: travel (1,0) -> (0,0) back to depot with load 40 kg at start: speed 10 − (40//10) = 6 m/min, distance 1, time ≈ 0.1667 min. Arrive, unload, load resets to 0.
  - Leg 3 (if there were a third item later in the trip, not in this example) would use the updated load.
This kind of sequence clarifies the “load update applies to the next leg” rule in a concrete, non-obvious scenario.

Bottom line
- The spec is largely coherent and implementable but has several ambiguities around edge-case mechanics (zero-distance legs, load progression in multi-item sequences), connection failure handling, and per-round validation details.
- Adding targeted examples, explicit handling notes, and a few clarifications as above will reduce misinterpretations and ensure consistent implementations across frontier LLMs.

========================================================================
# Grok  (:7823, logic, repo cross-ref, brutal honesty)  [8.5s]
========================================================================
!! ERROR: HTTPError: HTTP Error 502: Bad Gateway

========================================================================
# Perexp  (:7826, deep reasoning, code execution)  [16.2s]
========================================================================
Ambiguities
- The spec states speed(load_kg) = 10 − (load_kg // 10) and then clarifies certain load ranges, but it also says speed becomes 0 for load ≥ 100 kg. If a leg starts with load ≥ 100 kg and has positive distance, it’s invalid per the stuck rule. However, it’s unclear whether a leg with start load exactly 99 kg and distance > 0 is allowed (it would be 1 m/min). The boundary condition between 99 kg and 100 kg could be stated more crisply.
- “Pickup at B happens after arrival; the load update applies to the next leg.” This implies the load during the leg reaching B is the pre-pickup load, but it’s not explicit whether a very first item pickup in a trip changes the load for the subsequent leg immediately. The exact sequencing could be misread.
- The “zero-distance leg” rule says it’s fine at any load. It’s ambiguous whether a zero-distance leg still consumes time (it should be 0 distance, so 0 time). The spec says time for a leg is distance/speed, so a zero-distance leg yields 0 time, which is fine, but explicit confirmation would help.
- Items with identical coordinates are allowed, but there is no explicit rule about multiple items at the same bin causing instant successive pickups to affect load for the next leg. The text implies it, but an explicit example would help.
- The constraint “empty trips are not allowed” is stated, but it’s not stated whether a trip with multiple items where a later item has weight that would render the next leg invalid is allowed to include that sequence (the server enforces validity). It’s fine but could be clearer.

Underspecified edge cases
- Round timeout behavior: If the server times out during submission, is there any retry mechanism or any state retention? It says timeout yields INVALID timeout, but not whether the bot can re-submit within the same round after a short delay.
- Item weight boundaries: weights are integers, but there is no explicit handling of extremely heavy items that individually exceed 100 kg. If an item weight is ≥ 100 kg, the first leg to reach that item would have load < 100 during travel, but the final leg back could push to 100+. The “stuck” rule triggers only if start of a leg has load ≥ 100. If an individual item alone has weight ≥ 100, the first leg to reach it would be okay, but after pickup the return leg would start with load ≥ 100, potentially invalid if distance > 0. This should be explicitly stated.
- Handling of rounding errors: total_time is reported with 4 decimals. If very small floating errors occur, is there any tolerance in validation? The spec doesn’t mention tolerance; it assumes exact floating computation on server, but client might yield tiny discrepancies. Clarify acceptable floating precision or rounding behavior.
- Negative or non-integer coordinates: The spec says integers, but no explicit validation rule beyond server’s. It’s implied but not explicit.
- End-of-round timing: If you submit multiple TRIP lines after the last ITEM, what if you interpose extra whitespace lines? The validation says lines must match a strict regex; extra whitespace would cause malformation. This is implied but could be spelled out.

Protocol / interface gotchas
- Round header vs end: The server sends ROUND after END_ROUND; ensure you don’t send before ROUND. The spec says wait for ROUND after END, clear.
- Item indices: The spec requires indices 0..N-1 exactly once. Implementations should robustly check duplicates and missing items; the spec requires exact positioning for error tokens like missing_item_<idx>. Implementers must ensure their submission order is deterministic to match server expectations.
- End-of-round: After END, server replies OK or INVALID and then END_ROUND. If implementing client, ensure you read END_ROUND before proceeding to next ROUND. The spec implies synchronous per-round flow; any deviation will cause misalignment.
- Encoding and line endings: ASCII, LF only. Ensure your environment does not insert CRLF or extra whitespace. The server is strict; any stray spaces or tabs will cause malformed_trip_<i>.
- BOTNAME handling: The bot must read BOTNAME from env and not modify it. If missing, the bot should not attempt to connect. Ensure you handle the case where env var is empty gracefully (don’t connect).

Inconsistencies
- The table in §2 lists scores for ranks but does not specify tie-breakers beyond time order. They state ties on total_time break by earliest submission timestamp; this is consistent, but ensure your submission timestamps are correctly recorded by the server. No contradiction, but be aware: per-round scoring depends on time precision and submission order, which may interact with system clocks.
- The “stuck at trip” rule vs speed function: The text says speed for a leg is speed(load_at_A). If you pick up an item at the end of a leg, the next leg uses increased load. This is consistent with the example, but it’s easy to misinterpret. The spec does say the pickup applies to the next leg; ensure your implementation aligns with that exact sequencing.

Missing information that would help implement
- A precise example illustrating load progression within a trip with multiple items, including a case where two consecutive items share a bin (zero-distance leg) and how load updates across those legs.
- A formal definition of how time is accumulated for trips that contain zero-distance legs (though implied to be 0 time for those legs).
- Guidance on how to structure extremely large schedules: any practical constraints on the number of trips or line length? The spec implies any number as long as every item is covered; but an upper bound would help.

One concrete observation for implementers
- The prompt requires a complete, self-contained Python 3.10 bot that uses only the standard library and produces a full strategy. This is feasible but risky: designing an offline planner that minimizes total time is complex. The spec’s scoring is based on total_time; a naive implementation may still be accepted but with poor score. If you’re evaluating multiple frontiers, expect some to produce suboptimal but valid strategies.

Example quotes and what’s wrong
- Quote: “The bot starts every round at `(0, 0)` with load 0 kg, and at the end of every trip must be at `(0, 0)` to unload.” Issue: It implies you must always return to origin between trips. Some interpretations might allow combining trips or unloading differently; however, the spec clearly enforces per-trip returns, so implementers should lock to that.
- Quote: “Time for a leg of distance d meters at speed s m/min is d / s minutes.” Issue: If s = 0 (load ≥ 100 kg), this would be division by zero. The spec also states that legs with positive distance at load ≥ 100 kg are invalid. A robust implementation must ensure no leg with distance > 0 starts with load ≥ 100 kg; otherwise the server will reject. It would be clearer to state that such legs are never allowed and must be avoided.
- Quote: “An empty TRIP line is not allowed.” Issue: Fine, but the validator requires empty_trip_<i> if a TRIP with no items is detected. The line “not allowed” vs the validator token could be aligned by explicitly stating that empty trips yield invalid with reason empty_trip_<i>.

Illustrative example of a concrete edge case
- If an item has weight 105 kg, the trip to pick it up will end with load 105 kg, which makes the next leg (return to origin) start at load ≥ 100 kg. If the distance back is positive, that would violate the stuck rule. The server’s validation would reject this trip with a reason like stuck_at_trip_<i>_leg_<pos>_load_<L>. The spec mentions this, but it would be helpful to explicitly note items heavier than 100 kg are effectively impossible to carry unless paired with zero-distance returns or immediate zero-distance legs. Clarify how to handle items with weight ≥ 100 kg in the round design.

Bottom line recommendations for contributors
- Tighten boundary handling around loads approaching 100 kg, and explicitly specify behavior for items with weight ≥ 100 kg.
- Add explicit examples showing load progression within a round, including back-to-back pickups in the same bin and zero-distance legs.
- Clarify time semantics for zero-distance legs (time 0) and how they interact with floating-point accumulation across many trips.
- Consider adding explicit tolerances or validation notes for floating-point rounding to avoid subtle mismatches between client planner and server validation.

If you’d like, I can:
- Produce a clean, annotated checklist you can paste into a review doc.
- Create a concrete set of test cases (edge cases) to exercise the ambiguous/underspecified rules.
- Draft a minimal but compliant Python 3.10 bot template that adheres to the protocol, plus a simple baseline strategy to ensure valid submissions.

========================================================================
# Perexp2  (:7827, second independent opinion)  [19.5s]
========================================================================
Here is a structured critique of the prompt, focusing on ambiguities, underspecifications, gotchas, inconsistencies, and missing information. I quote exact text sections and explain what’s wrong or unclear. I’ll not rewrite the spec, but point out concrete issues you’d want resolved before sending to LLMs.

1) Ambiguities

- Quote: “The bot connects to the tournament server at `localhost:7474`.” 
  Issue: What if the server is not available at that moment? Should the bot retry, backoff, or fail fast? No retry policy is specified.

- Quote: “The bot’s submission is one or more `TRIP` lines followed by a single `END` line.” 
  Issue: Is a trailing newline after `END` required? Are extra blank lines allowed before `END`? The spec does not specify tolerance for extra whitespace beyond the stated strict line formats elsewhere.

- Quote: “The server replies with one of: `OK <total_time> <trip_count>` or `INVALID <reason>`.” 
  Issue: If multiple invalid reasons apply, which one is chosen? The spec says first failure determines INVALID, but the client doesn’t know until after sending. This ambiguity is on validation logic, not on the server, but it affects how a bot might self-check.

- Quote: “The bot has 30 seconds wall-clock from the instant the server has finished sending the last `ITEM` line to the instant the server has finished reading the bot’s `END` line.” 
  Issue: Does 30 seconds include time spent sending the `TRIP` lines? It says yes: “wall-clock … compute time and any time spent transmitting.” This can be confusing for agents that attempt to minimize compute time vs. I/O time. The exact boundary (counting the final flush) is not explicit.

- Quote: “The speed(load_kg) = 10 − (load_kg // 10).” 
  Issue: The description says speed becomes 0 for ≥100 kg, which would freeze the robot. It later says “The robot’s speed is speed(load_at_A).” Then, “The pickup at B happens after arrival; the load update applies to the next leg.” However, the text also contains a separate rule under Stuck: “If at the start of any leg the robot’s load is ≥ 100 kg AND the leg has positive distance, the trip is invalid.” This is marginally redundant with the speed zero rule, but the interaction with zero-distance legs vs. positive-distance legs is not perfectly aligned in phrasing. Ambiguity remains about exactly which leg distance counts and at what load, if a leg has distance zero when dropping off a bin with weight that would raise load to 100+.

- Quote: “Empty trips are not allowed.” 
  Issue: If a bot submits a malformed submission with no items across all trips, is that treated as empty trips, or exactly as described? The “END” line possibility is described later, but the edge-case behavior when there are zero trips is not explicit beyond “not allowed.”

2) Underspecified edge cases

- Start of round: If the server times out waiting for the bot’s `END` and marks it invalid, how should the bot handle reconnection or resubmission for the same round? The spec says invalid round forfeits points but the bot remains connected; it doesn’t specify reconnection logic or state resets between rounds.

- Zero-distance legs within a trip: It says zero-distance legs are fine at any load. Do zero-distance legs affect time calculation? Implicitly time is zero, but not explicitly stated.

- Trip validity with total load on leg: The Stuck rule mentions the start-of-leg load when it’s ≥ 100 kg and the leg has positive distance. It does not specify what happens if a leg has distance zero but the next leg (after pickup) would be positive. The traversal might include multiple consecutive zero-distance legs in a trip; the exact load checks for each positive-distance leg are implied but not formally enumerated.

- Item weight handling: When exactly is the load updated? It says “pickup at B happens after arrival; the load update applies to the next leg.” If two consecutive items share a bin, the distance is zero, but the load increases after arrival at the bin. If the next leg is non-zero distance, the speed should be based on the prior leg’s load (i.e., the load before picking up the next item). This is consistent, but the description could be clearer with a small formal timeline example.

- Rounding/formatting of OK line: “<total_time> is rendered as a float with 4 decimal places.” It doesn’t specify the locale (decimal point). It’s assumed, but not explicit.

3) Protocol / interface gotchas

- Round order and trip order: It says “Trip-order does not affect the score (each trip starts and ends at (0, 0) with load 0), but the order is preserved in the log for replay.” However, it also says “The server uses the order verbatim and does not reorder.” The potential gotcha is that an implementer might assume the server can reorder, but here it’s the bot’s own submission order that matters for log, not the score. The spec could be clearer about whether the server replays trips in submission order or uses the per-trip data as recorded for scoring. The phrase “server uses the order verbatim and does not reorder” resolves it, but it’s an important nuance.

- Validation; item index range: If the bot uses indices outside 0..N-1, it’s rejected with bad_item_<i>_<pos>. It’s up to implementers to ensure no duplicates; but there’s no explicit enforcement that each index appears exactly once except through server validation. This is standard, but could be clearer with an explicit example sequence.

- Input line constraints: “Lines have no leading or trailing whitespace beyond the single terminating `\n`.” This means trailing spaces or tabs on a line render as malformed. Implementers must be precise about line endings; some languages produce trailing spaces unless careful.

- Time accounting: The “total_time” includes compute time and transmission time. A bot that uses heavy computation could inadvertently violate 30s budget in practice even if the simulator would allow. This is unusual for typical contest specs and could trip border cases.

4) Inconsistencies

- The speed function gives 0 speed for load ≥ 100 kg, yet the Stuck rule specifically disallows starting a leg with load ≥ 100 kg and positive distance. Those two rules align conceptually, but the exact boundary condition could be enforced slightly differently in implementations. The spec is internally consistent but could be tightened to avoid confusion: explicitly state that any leg with positive distance must begin at load ≤ 99 kg.

- Item weight ranges: It says weights are integers, but there is no explicit maximum weight per item listed, though the speed function bounds usage to 0–99 kg for meaningful movement. It’s implied that items could push the load over 100 kg, but not explicitly bounded by any per-item maximum. The edge case of a single item with weight ≥ 100 kg would cause the first leg (0,0) to item bin to be impossible if distance > 0, since speed would be 0? Actually speed at load 100 is 0 so the first leg would be infinite time, effectively invalid. The spec does not explicitly forbid such a case, but it would be rejected by the “start of leg load ≥100 with positive distance” rule; as a single-item trip, the leg to reach the item would be invalid. This is consistent but not explicitly stated elsewhere.

5) Missing information

- Error handling on disconnects: If the server closes the connection, should the bot attempt to reconnect or exit? Not specified.

- Bot naming constraints: It requires BOTNAME to be 1–32 characters from [A-Za-z0-9_-]. It doesn’t specify what happens if the environment variable contains newlines or non-ASCII characters; it says “exact bytes … verbatim.” The validation would reject invalid characters. But it would be good to specify how to sanitize or warn on invalid characters prior to connection.

- Example of a complete, valid submission beyond the sample: A truly helpful enhancement would be a minimal valid round with a small set of items to demonstrate, but the spec provides only one small example. More examples would help writers avoid subtle mistakes.

- Time units consistency: The score is total_time in minutes, but the sample shows 14.3833 minutes. The server formats to 4 decimals. It’s consistent, but clarifying that all internal computations use floating-point arithmetic and that rounding occurs only on the final OK line would be helpful.

6) Potential contradictions

- None of the statements directly contradict each other, but several statements rely on implicit assumptions (e.g., exact handling of zero-distance legs, when load updates occur) that could lead to two implementations diverging in subtle ways.

7) Specific actionable issues (quoted examples)

- Ambiguity: “A zero-distance leg (the next pickup is at the current position because two consecutive items share a bin) is fine at any load.” 
  What about the time to traverse a zero-distance leg? Implicitly zero, but not explicit. Recommend: state explicitly that distance 0 yields 0 time, regardless of speed.

- Edge-case: “The pickup at B happens after arrival; the load update applies to the next leg.” 
  Clarify with a concrete timeline or a tiny formal rule set to avoid misinterpretation about the load used for the leg arriving at B vs. the next leg.

- Gotcha: “The first failure determines INVALID” is described in §6, but the bot may not know until after submission. It is fine, but the spec could include a recommended pattern for partial validation or dry-run checks before submission to reduce risk of getting an INVALID due to a single malformed line.

8) Summary assessment

- Strengths: Clear round structure, explicit per-round protocol, and explicit validation failure reasons. The 30-second budget with a strict line protocol is well defined. The independence of trips simplifies reasoning.

- Key risks for implementers: Subtle timing semantics (load, speed, and leg ordering), edge cases around zero-distance legs, strict formatting rules (no whitespace, exact line endings), and the 30-second wall-clock budget that includes I/O time.

- Recommendations before finalizing: Add precise timing rules for zero-distance legs, formalize the exact state transition for load and position after each pickup, and add a short, concrete example of a round with multiple trips that exercises all edge cases. Consider adding an explicit reconnection/backoff policy, and explicitly state whether trailing newlines or extra blank lines are allowed (likely not). Provide a minimal working example or a formal state machine snippet to guide implementers.

If you want, I can produce a concise checklist or a formalized edge-case spec (in plain language, not code) to help implementers align with your intent, or generate a critique focused on a particular aspect (e.g., timing semantics or protocol correctness). Would you like that?
