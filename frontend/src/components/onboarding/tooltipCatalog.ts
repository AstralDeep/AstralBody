/**
 * tooltipCatalog — frontend-owned tooltip strings for static UI surfaces.
 *
 * Server-driven (SDUI) components carry their own tooltip text on the
 * backend `Component.tooltip` field; this catalog is for the static
 * dashboard chrome (sidebar, header, modals).
 *
 * Keys are stable, namespaced identifiers (e.g. `sidebar.audit`). The
 * `Tooltip` wrapper renders nothing when the lookup is empty, so a key
 * being absent from this catalog is the correct way to signal "no
 * tooltip" (FR-008).
 */

export const tooltipCatalog: Record<string, string> = {
    // Sidebar entries
    "sidebar.agents": "Browse, configure, and grant scopes to agents.",
    "sidebar.audit":
        "Review every action your agents have taken on your behalf, recorded and signed.",
    "sidebar.feedback-admin":
        "Admin: review flagged tools, knowledge proposals, and quarantined feedback.",
    "sidebar.tutorial-admin":
        "Admin: edit the copy of every step in the getting-started tour.",
    "sidebar.replay-tour": "Replay the getting-started tour from the beginning.",
    "sidebar.new-chat": "Start a new conversation with an agent.",
    "sidebar.toggle": "Show or hide the sidebar.",
    "sidebar.logout": "Sign out of AstralBody.",

    // Chat surfaces
    "chat.input": "Type a message and press Enter to send it to an agent.",
    "chat.send": "Send your message.",
    "chat.cancel": "Cancel the current task and stop the agent.",

    // Feedback control surfaces (feature 004)
    "feedback.control": "Tell us this component was useful — or wasn't.",
    "feedback.thumbs-up": "Mark this component as useful.",
    "feedback.thumbs-down": "Flag this component as wrong, irrelevant, or broken.",

    // Admin tutorial editor (feature 005, surfaced in Phase 6)
    "admin.tutorial.new-step": "Add a new tutorial step.",
    "admin.tutorial.archive": "Archive (soft-delete) this step. It can be restored later.",
    "admin.tutorial.restore": "Restore an archived step so it appears in the tour again.",
};
