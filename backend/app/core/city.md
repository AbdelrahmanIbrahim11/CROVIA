# City Geography Module (`/backend/app/core/city.py`)

This module defines the physical hierarchy of the city. It acts as the static foundation that the AI and detection rules use to understand the physical constraints of where crowds are gathering.

## Core Philosophy: The Single Source of Truth
By loading all geographic data from a shared JSON file (`lusail.geo.json`) upon startup, the backend, the visual dashboard (Expo app), and the crowd simulator all share a single source of truth. They can never disagree on a street's location or its width.

---

## The Physical Hierarchy (Container Structure)

### 1. City
*   **Purpose**: The master container that loads and holds the entire map in memory via its constructor.
*   **Key Insight**: It provides mathematical lookup functions. The most important formula it holds is: `capacity = width * 72`. This asserts that a street can safely pass about 72 people per meter of width per minute. Knowing this static fact allows the system to calculate crowd danger instantly without spending API budget.

### 2. District
*   **Purpose**: The macro-level container (a broad neighborhood).
*   **Data**: Defined by a center point (`LatLon`) and a large radius.
*   **Role**: Used to track broad congestion levels. Because raw telecom network pushes lack precise GPS coordinates, they can only be mapped to these larger district-level boundaries to act as an early warning system.

### 3. Zone
*   **Purpose**: The specific area of interest (e.g., a stadium concourse or a metro entrance).
*   **Data**: Defined by a center point and a specific radius. It is nested inside a parent `District`.
*   **Role**: This is the exact geographical circle that the AI asks the engine to investigate. The engine uses this radius to ask the CAMARA network, *"Are these devices inside this specific circle?"*

### 4. Segment (The Bottleneck)
*   **Purpose**: A line-like structure representing the actual walkable links (streets, ramps, gates) inside a zone.
*   **Data**: Defined by start/end points and a physical width (`width_m`).
*   **Role**: A zone might contain many segments, but the system finds the narrowest one—**the bottleneck**. By knowing the physical width of this bottleneck, the system immediately knows the maximum number of people that can safely escape the zone per minute.

---

## Dynamic Operations

### Operator-Drawn Zones
While the core city map is static, operators can dynamically draw new temporary zones on the map during an unfolding event.
*   **The Safety Check**: When drawing a zone, the operator is *forced* to explicitly input the width and length of the physical bottleneck. The system refuses to guess these numbers. This ensures that manually drawn emergency zones are subjected to the exact same rigorous mathematical safety rules as the pre-planned city zones.

