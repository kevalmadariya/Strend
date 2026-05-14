# Spec: Context Overflow Handling for PlanningAgent

## Problem Statement
The `PlanningAgent.run` method builds a growing conversation history across multi‑turn interactions. Over long conversations (dozens of turns), the prompt sent to the LLM may exceed the model’s maximum token limit. This causes a “context overflow” error, abruptly terminating the conversation and losing all accumulated state. A mechanism is needed to gracefully prevent the context from exceeding the token limit while preserving the essential information required for accurate reasoning and tool usage.

## Functional Requirements
- **FR1 – Token Budget Monitoring**  
  Before each LLM call, the system must estimate the token count of the entire prompt (system message + full history). The estimate must be compared against the LLM’s maximum context length.

- **FR2 – Proactive Truncation/Summarisation**  
  When the estimated token count approaches a configurable threshold (e.g., 80% of max tokens), the system must automatically reduce the context. Acceptable strategies include:
  - Summarising older messages into a concise “conversation summary” and replacing the discarded history with a single system or human message containing that summary.
  - Retaining the most recent N turns while discarding or summarising everything before.
  The exact algorithm must be tunable (e.g., summarisation model, retention window size).

- **FR3 – Continuity Preservation**  
  After reduction, the system must retain all critical information:
  - The current task and pending tool call status.
  - Key facts discovered earlier (e.g., tickers, dates, computed columns).
  - Any unsolved missing parameters still expected from the user.

- **FR4 – Transparent Operation**  
  The context handling must operate silently (no user‑visible messages about summarisation) unless an error recovery is required. The conversation must appear seamless.

- **FR5 – Configurability**  
  The following must be configurable per agent instance:
  - `max_context_tokens`: the absolute token limit for the LLM.
  - `overflow_threshold_ratio`: the fraction of `max_context_tokens` at which reduction is triggered (default 0.8).
  - Reduction strategy (e.g., `"summarise"`, `"trim"`).

## Input/Output Behavior
- **Input**  
  The `run` method continues to receive a `user_input` string. Internally, the conversation history accumulates as usual.

- **Processing**  
  Before invoking the LLM:
  1. Token count of `SystemMessage + full history` is estimated.
  2. If count > `max_context_tokens * overflow_threshold_ratio`:
     - The history is reduced according to the chosen strategy.
  3. The (potentially reduced) history is sent to the LLM.

- **Output**  
  The method yields the same kinds of output (tool results, final answers). The user does not perceive the context reduction unless the reduction itself fails and an error is raised.

## Constraints
- The token estimation must be compatible with the LLM’s tokeniser (or a reasonable approximate tokeniser) without adding significant latency.
- The reduction process must not introduce new conversation turns visible to the end user.
- The implementation must work with both synchronous and asynchronous tool functions.
- The chosen reduction strategy must preserve the system prompt and at least the last complete exchange (user request + tool result + AI reasoning) to avoid losing the immediate task.
- Performance: token counting and reduction must complete in under 1 second on typical hardware.

## Edge Cases
- **History exactly at the limit** – The reduction must still apply and produce a valid prompt.
- **Very long tool results** – A single tool result message could itself exceed the token limit. The system should handle this by truncating or summarising the tool result (e.g., keeping the first N characters and adding a note that the output was truncated).
- **First turn already over limit** – If the system prompt plus the first user message exceeds the threshold, the system should still attempt to send it (but may ultimately fail; at minimum it must not crash).
- **Reduction fails** – If the summarisation call to the LLM fails, the system should fall back to a simpler trim strategy (discarding oldest messages while keeping the most recent ones) and log a warning.
- **Loss of critical data** – After trimming, the LLM may ask for information already provided. The system must accept that this is a trade-off and not loop indefinitely; it may need a secondary strategy to re‑inject lost facts (e.g., storing key facts in a separate “memory” that is always included). The spec does not require perfect memory, only that the conversation does not crash due to overflow.
- **Maximum reasoning turns limit** – The existing `max_turns` loop (10) remains unaffected; overflow handling is separate.

## Acceptance Criteria
1. **AC1 – No Token Limit Crashes**  
   A long conversation (≥ 30 turns with verbose tool outputs) completes without an API error caused by exceeding the model’s token limit, as long as each individual turn is valid.

2. **AC2 – Continuous Operation**  
   After every context reduction, the agent continues reasoning correctly. For example, after summarising, the agent still knows it was working on a multi‑step task and can finish it.

3. **AC3 – Configurability Works**  
   Changing `overflow_threshold_ratio` or `max_context_tokens` alters when reduction triggers, and changing the strategy switches between summarisation and trimming.

4. **AC4 – Observation Preservation**  
   After a reduction, the immediate next LLM call produces a response that is consistent with the conversation history before reduction (no confusion about pending actions).

5. **AC5 – Edge Case Handling**  
   - A tool result larger than the token limit is presented as “(output truncated)” and the agent can still proceed.
   - A history exactly at the threshold triggers reduction.
   - If summarisation fails, a fallback trim is used and logged.