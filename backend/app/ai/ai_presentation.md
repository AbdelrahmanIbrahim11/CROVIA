# Crowd Safety AI Architecture: Presentation Guide
**Directory:** `/backend/app/ai/`

This document provides a high-level, efficient breakdown of the entire AI architecture, tailored specifically for presentations. It synthesizes the mechanics of both `tools.py` and `graph.py` into key concepts and talking points.

---

## 1. The Core Philosophy
**"Choice vs. Decision"**
*   The AI Agent is responsible solely for **Choice**: Where should we look? Which sensor tool should we use? How much API budget should we spend?
*   The AI is strictly prohibited from making the final **Decision**: Determining if a crowd is actually dangerous.
*   *Why?* Crowd safety verdicts must be transparent, mathematical, and auditable. We cannot trust a black-box LLM to declare an emergency. The architecture physically forces the AI to hand its gathered evidence to a hard-coded deterministic rule engine (`detect.danger.assess`) for the final verdict.

---

## 2. The Tool Escalation Ladder (`tools.py`)
The system uses an escalating suite of tools to balance safety with API budget efficiency.

1.  **`arm_chokepoints` (The Tripwire)**
    *   **Cost**: Free.
    *   **Function**: Retrieves physical bottleneck widths and max capacities from static city maps. Escalates the parent district's status to "WATCHING".
2.  **`verify_and_filter` (The Data Gatherer)**
    *   **Cost**: Moderate.
    *   **Function**: Uses the CAMARA network to ping a random "panel" of devices to estimate the crowd size. Logs timestamps and headcounts to calculate the flow rate (how fast the crowd is growing).
3.  **`retrieve_locations_batch` (The Heavy Sensor)**
    *   **Cost**: High (Reserved only for active surges).
    *   **Function**: Retrieves highly precise GPS-style coordinates.
    *   **Smart Mechanics**: It oversamples candidates (3x) and pre-filters for reachable devices (which is free) before paying for location data. It returns the **median accuracy** to prevent a single bad cell-tower ping from skewing the accuracy metrics.
4.  **`judge` (The Messenger)**
    *   **Cost**: Free.
    *   **Function**: Bundles the evidence and passes it to the deterministic math rules. 

---

## 3. The Orchestration Brain (`graph.py`)
The logic engine that commands the tools.

### A. The LLM Agent (`ModelPolicy`)
*   Powered by LangChain and Groq (`temperature=0` for strict, mathematical logic).
*   It consumes a plain-English translation of the city's live database (`_describe()`).
*   It is artificially constrained to output a single decision per cycle using a pipe delimiter (e.g., `Zone | Tool | Reasoning`).

### B. The Dual-Layer Safety Net
The system is built for critical resiliency.
*   **Startup Fallback**: If the API key is missing or invalid on boot, the system abandons the AI and boots a mathematical rules engine (`DeterministicPolicy`).
*   **Runtime Fallback**: If the AI hallucinates, or the API server crashes during an active stadium crush, a `try/except` block instantly catches the failure and routes command to the mathematical rules, ensuring the city is never left unmonitored.

### C. The Deterministic Rules (`DeterministicPolicy`)
The mathematical safety net that mirrors the AI's logic:
*   **Network Fault Detection**: If all districts spike simultaneously, it suppresses action, recognizing a telecom fault rather than a crowd.
*   **Baseline Comparison**: It ignores zones unless their congestion is at least double that of the calmest part of the city.
*   **Immediate Escalation**: If a crowd is filling at >45% of the street's physical capacity, it skips cheap tools and instantly deploys the heavy GPS sensors.

### D. The Governor (`run_once`)
The central loop that executes the policy.
*   **Budget Pacing**: Even if the rules identify 10 dangerous zones, the orchestrator artificially caps execution at the top 3 (`[:3]`) per cycle. This prevents the system from burning through its entire hourly API budget in a single second.
*   **Automated Accounting**: It acts as a ledger, subtracting the budget total before and after a tool runs to log exact financial costs per decision.

---

## 4. Key Presentation Talking Points (Summary)
When pitching or explaining this architecture, emphasize these three pillars:
1.  **Auditability**: The AI acts only as an investigator; the final danger verdict is always deterministic math.
2.  **Financial Efficiency**: We don't blind-fire expensive APIs. We use free static data first, escalate to moderate statistical sampling, and only pay for high-precision GPS when a surge is mathematically proven. We also pre-filter unreachable devices before spending money.
3.  **Critical Resiliency**: The system features a dual-layer fallback. A provider outage or LLM hallucination cannot take the detection engine offline.

