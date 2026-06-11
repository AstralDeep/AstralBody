# SDUI Evolution Proposal: Sessions, History, and Utility (Branch 027)

## 1. Context: Branch 027 Analysis
Branch `027-agentic-creation-settings` has already introduced critical infrastructure that the main branch lacks:
- **`HistoryManager` with DB Backend:** A robust migration from JSON to Postgres.
- **`saved_components` Table:** The system already has the ability to `save_component`, `get_saved_components`, and `replace_components` in the database.
- **Session Binding:** Chats are now bound to `agent_id` and `user_id`.

**The Gap:** While the *data* is being saved in the backend, the *frontend* is still treating the UI as a transient "current message" view. The "saved components" exist in the DB but aren't being used to maintain a persistent, evolving workspace during a live session.

---

## 2. Core Pillar: Session-Based UI History
Instead of a linear chat where the UI is a byproduct of the last message, we move to a **Stateful Session Model**.

### The "UI Timeline"
- **State Snapshots:** For every turn in a chat, the backend should save a snapshot of the "Active Workspace" (which components were visible and their current values).
- **Time-Travel UI:** Implement a "UI History" slider or button. Because `saved_components` are already indexed by `chat_id`, the frontend can request the state of the workspace at `T-minus-N` messages.
- **Session Re-hydration:** When a user re-opens a chat, the system doesn't just load text messages; it re-hydrates the `saved_components` into the workspace, restoring the exact tool-state the user left behind.

---

## 3. Core Pillar: The Persistent Workspace (Canvas)
To stop the "disappearing UI" problem, separate the **Conversation** from the **Workspace**.

### The Architecture
- **The Stream (Left/Bottom):** Standard chat history. Text, small alerts, and status updates.
- **The Canvas (Right/Main):** A persistent area where `saved_components` live.
- **Update Logic:**
    - When the agent sends a primitive, it must include a `component_id`.
    - If the ID exists in the Canvas, the frontend **updates it in place** (no flicker, no disappearance).
    - If the ID is new, it is **pinned** to the Canvas.

---

## 4. Core Pillar: Making SDUI "Actually Useful"
To make components feel like apps rather than static reports, implement a standardized **Interaction Loop**.

### The Action-Event Contract
Components should be "Event Emitters."
- **Interaction:** A user clicks a "Refresh Data" button in a `Table` component.
- **Event:** Frontend sends `{ "type": "ui_event", "component_id": "table_1", "action": "refresh", "payload": { ... } }`.
- **Orchestration:** The orchestrator treats this as a high-priority user intent $\rightarrow$ triggers the relevant tool $\rightarrow$ pushes a `replace_components` update to the database and the UI.

### Dynamic Utility Enhancements
- **Client-Side State:** Allow components to handle "shallow state" (e.g., sorting a table, toggling a dropdown) locally in React without hitting the backend.
- **Cross-Component Links:** Allow a button in `Component A` to update the data in `Component B` via the backend orchestrator.

---

## 5. Implementation Roadmap for Branch 027

### Phase 1: Frontend State Decoupling
- [ ] Modify the frontend to maintain a `workspaceMap: Record<string, Component>` separate from the `messages` array.
- [ ] Update the `DynamicRenderer` to handle `UPSERT` logic based on `component_id`.

### Phase 2: History Integration
- [ ] Extend `HistoryManager.get_chat` to explicitly return the `saved_components` for that session.
- [ ] Create a "History/Version" UI element that lets users toggle between different versions of a component's state.

### Phase 3: The Interaction Loop
- [ ] Implement the `ui_event` WebSocket message type.
- [ ] Update the `coordinator.py` to handle `ui_event` messages as trigger inputs for the agent's tool-use loop.
