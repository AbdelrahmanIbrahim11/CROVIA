# AI Decision Graph (`/backend/app/ai/graph.py`)

This module houses the "brain" of the crowd-safety system. It dictates how the system decides which zones to investigate and which tools to use.

## Architectural Philosophy: Choice vs. Decision
The strict boundary enforced by this module is that the AI agent is only responsible for **choice** (where to look, which tool to use, how much API budget to spend). It is never allowed to make the final **decision** (whether a crowd is actually dangerous).

---

## 1. The Dual-Layer Safety Net (`build_policy`)
The system is protected from AI failures at two different levels:
*   **At Startup**: When the app boots, `build_policy()` checks for a valid Groq API key. If it's missing or fails to connect, it abandons the AI and boots up the `DeterministicPolicy` (the math-based rules) instead.
*   **At Runtime**: If the AI boots successfully but the API goes down during a live emergency, the `ModelPolicy` has a `try/except` block that instantly catches the failure and routes the decision back to the rules.

## 2. The Policies (The "Brains")
Both policies share the same interface: they look at the city and return a list of `Decision` objects (which contain the Zone ID, the Tool, and the Reasoning).

### The AI Agent (`ModelPolicy`)
*   **Input**: The system engine.
*   **The `decide()` Method**: It feeds the `SYSTEM_PROMPT` and the translator's output into a Large Language Model (via LangChain). It asks the AI to intelligently reason about the city's state and select the best tool. If the API fails for any reason, it automatically falls back to the `DeterministicPolicy`.
*   **The Delimiter**: Because LLMs return plain text, the code forces the AI to answer using a pipe (`|`) as a delimiter (e.g., `zone_stadium | verify_and_filter | Congestion is high`). The code then splits this string by the pipe to extract the 3 pieces of data and packages them into a `Decision` object.

### The Rules-Based Fallback (`DeterministicPolicy`)
*   **Input**: The system engine and a frozen snapshot of the city's state.
*   **The `decide()` Method**: This mathematical policy replicates the AI's logic to keep the city safe if the AI is offline.
    1.  **Fault Check**: If every district reports high network congestion simultaneously, it recognizes a telecom network fault and suppresses action to save budget.
    2.  **Baseline Check**: It compares a district's congestion to the calmest part of the city. If it is not unusually high and the crowd is not actively growing, it ignores the zone.
    3.  **Initial Counting**: If a zone is suspicious but lacks historical data (fewer than 2 previous counts), it calls `verify_and_filter` to establish a baseline.
    4.  **Danger Escalation**: If the crowd's fill rate approaches 45% of the physical street's capacity, it senses immediate danger and escalates to the expensive `retrieve_locations_batch` tool for exact GPS coordinates.
    5.  **Maintenance**: If the situation is moderate, it calls `verify_and_filter` again to keep the flow rate data current.

## 3. The Orchestrator (`run_once`)
This is the main execution loop that enforces the system's safety boundaries.
*   **Input**: The live system engine.
*   **Process**: 
    1.  **The Governor**: It asks the active policy for its decisions, but strictly caps execution at the top 3 (`[:3]`). If the deterministic rules return 5 dangerous zones, it only runs the first 3 to prevent bankrupting the API budget in a single second.
    2.  **Execution & Accounting**: It checks the ledger's total spent before running the tool, executes the tool, and then checks the ledger again. It subtracts the two to calculate exactly how many API calls were burned (`d.spent`).
    3.  **The Enforcer**: It automatically forces the `judge` tool to run immediately afterward. The AI cannot bypass this step; the deterministic mathematical rules always have the final say on danger.
*   **Returns**: A log of the executed decisions, the budget spent, and their final danger verdicts.

## 4. The Translator (`_describe`)
*   **Input**: The system engine and a `snapshot` (a dictionary representation of the city's state).
*   **Process**: 
    *   **Frozen State:** It takes a `snapshot` passed from the orchestrator rather than querying the engine directly. This ensures the AI reasons over a frozen, consistent moment in time and keeps the function clean and free of side effects.
    *   **Formatting:** The AI cannot natively read databases, so this function translates raw numbers into plain English. It gathers the district congestion percentages, the exact headcount of every zone, the physical bottleneck limits, current flow rates, and the remaining API budget for the hour.
*   **Returns**: A highly readable text summary of the city's exact state that gets injected straight into the AI's prompt.
