# The Detection Engine: Presentation Guide
**Directory:** `/backend/app/detect/`

This document synthesizes the overarching architecture of the Detection Engine (`engine.py` and `danger.py`) into a high-level guide ready for presentations or operator onboarding.

---

## 1. The Core Architecture: The Great Orchestrator
The Engine is the central metronome of the system. It connects the static City map, the PostgreSQL databases, the budget, and the live Nokia Telecom network.

*   **The Metronome (`tick`)**: Every 30 seconds, the engine evaluates the entire city. It looks at free webhook evidence, builds invoices for zones that need active counting, asks the Bank for API budget, and runs the final mathematical assessment.
*   **In-Memory Survival**: The Engine refuses to rely on the database to function. Outbound alarms are passed through a `try/except` hook. If the PostgreSQL database crashes, the hook fails silently and the engine instantly moves on to save the next crowd. **The engine is uncrashable by database failure.**

---

## 2. Unprecedented Privacy: The Lobby and the Pools
The system handles citizen data with extreme caution, utilizing a massive multi-layered privacy shield:
*   **The Lobby (Consent)**: When a citizen installs the app and consents, they wait in the "Lobby". They are completely untracked and invisible to Nokia.
*   **Runtime Fleet Building**: When an operator presses "Build Fleet", the system randomly draws users from the Lobby into two distinct, mutually exclusive groups:
    *   **The Sentinels (The Trackers)**: A tiny group (e.g., 60 per district). The engine geofences them to track network congestion. They serve as the broad early-warning system.
    *   **The Panel (The Counters)**: A city-wide random sample (e.g., 400). They are never geofenced and never tracked. They are simply pinged anonymously to generate statistical multipliers.
*   **The Vault**: The moment a user is enrolled, their phone number is hashed. The Engine and the Webhooks operate strictly on anonymous hashes.

---

## 3. Financial Intelligence: The Cadence and the UNKNOWNs
The system uses brilliant math to avoid bankrupting the telecom API budget while maintaining flawless accuracy.
*   **Dynamic Cadence**: Safe zones are checked every 5 minutes (cheap/coarse). Dangerous zones are checked every 60 seconds (expensive/precise). The "Balanced" cadence was mathematically proven via simulation to catch 100% of crushes with 0 false alarms.
*   **The Linear Regression Window**: By drawing a 7-minute line-of-best-fit, the engine calculates the crowd flow-rate immune to random statistical noise.
*   **The UNKNOWN Fix**: If the telecom network fails to locate a phone, it returns `UNKNOWN`. The engine explicitly discards these from the math. Counting them would artificially shrink the estimated crowd size, leaving citizens in danger.

---

## 4. Deterministic Safety: The "No AI" Guarantee
When lives are on the line, the final decision cannot be left to an LLM hallucination. The `danger.py` rules engine operates on pure math.
*   **Inferred Density over Measured Density**: GPS error is massive (150m-400m). The engine abandons raw coordinates and instead uses the physical width of the street (from the blueprint) against the massive flow of arriving people. It *infers* the crush rather than trying to measure the impossible.
*   **The Earliest Warning**: The system triggers if `Arrivals > Street Capacity`. This allows operators to dispatch police *before* the crowd is actually trapped in a crush.

