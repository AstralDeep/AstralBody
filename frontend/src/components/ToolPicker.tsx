/**
 * ToolPicker — popover that lets the user narrow which agents and tools
 * the chat dispatches to (Feature 013 / US4 + follow-up).
 *
 * Two stacked sections:
 *  - Agents: per-user, agent-wide on/off switches. Mirrors the toggle
 *    in the agent manager modal — disables the agent for this user
 *    without changing scopes/permissions.
 *  - Tools: per-tool checkboxes scoped to the *enabled* agents.
 *    Tools from disabled agents are hidden (the agent toggle is the
 *    coarse-grained control; tool checkboxes are the fine-grained one).
 *
 * Tool-selection rules (unchanged from US4):
 *  - `selectedTools === null` ⇒ no narrowing; orchestrator uses the
 *    full permission-allowed set (FR-019).
 *  - A non-empty array ⇒ explicit subset; orchestrator narrows to it
 *    (FR-018) — never widening.
 *  - An explicitly empty array ⇒ user has deselected everything; the
 *    parent must disable send (FR-021).
 */
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Wrench, RotateCcw, Info, Check, Bot } from "lucide-react";

export interface ToolPickerTool {
    name: string;
    description?: string;
    /** Optional agent the tool belongs to — used for grouping in the popover. */
    agentId?: string;
    agentName?: string;
}

export interface ToolPickerAgent {
    id: string;
    name: string;
    disabled: boolean;
}

export interface ToolPickerProps {
    /**
     * Agents the user can enable/disable for this chat. When empty, the
     * Agents section is omitted. Disabling an agent here calls the same
     * per-user, per-agent pref the agent manager modal uses — they stay
     * in sync.
     */
    agents?: ToolPickerAgent[];
    /** Fired when the user flips an agent's toggle. */
    onAgentToggle?: (agentId: string, enabled: boolean) => void;
    /** All tools permitted by scope + per-tool permissions, scoped to *enabled* agents. */
    permittedTools: ToolPickerTool[];
    /**
     * The current tool selection.
     *  - `null`  ⇒ no narrowing (default; FR-019).
     *  - `[]`    ⇒ user has deselected everything (caller blocks send per FR-021).
     *  - `[…]`   ⇒ explicit subset.
     */
    selectedTools: string[] | null;
    /** Fired when the user toggles a checkbox or clears the selection. */
    onChange: (next: string[] | null) => void;
    /** Fired when the user clicks "Reset to default" (FR-025). */
    onReset: () => void;
    /** Whether the popover is currently open. */
    open: boolean;
    /** Fires on outside-click / Escape so the parent can close the popover. */
    onClose: () => void;
    /**
     * Ref to the trigger button. The popover portals to `document.body` to
     * escape the chat panel's `overflow-hidden`, so we anchor it manually
     * using the trigger's bounding rect.
     */
    triggerRef?: React.RefObject<HTMLElement | null>;
}

/**
 * A focused tool-picker popover. Uses native checkboxes for accessibility
 * and reuses lucide icons + Tailwind utility classes already in the app
 * — no new primitive components introduced (Constitution VIII).
 */
export default function ToolPicker({
    agents = [],
    onAgentToggle,
    permittedTools,
    selectedTools,
    onChange,
    onReset,
    open,
    onClose,
    triggerRef,
}: ToolPickerProps): React.ReactElement | null {
    const popoverRef = useRef<HTMLDivElement | null>(null);
    const [rect, setRect] = useState<DOMRect | null>(null);

    // Measure the trigger before paint so the portaled popover never flashes at (0,0).
    useLayoutEffect(() => {
        if (!open || !triggerRef?.current) {
            setRect(null);
            return;
        }
        setRect(triggerRef.current.getBoundingClientRect());
    }, [open, triggerRef]);

    // Outside-click closes the popover. Trigger clicks are excluded so the
    // button's own onClick can toggle without this handler racing it closed.
    useEffect(() => {
        if (!open) return;
        const onClick = (e: MouseEvent) => {
            const target = e.target as Node;
            if (
                popoverRef.current &&
                !popoverRef.current.contains(target) &&
                !triggerRef?.current?.contains(target)
            ) {
                onClose();
            }
        };
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("mousedown", onClick);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("mousedown", onClick);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [open, onClose, triggerRef]);

    // Close on scroll/resize — repositioning is unnecessary because the trigger
    // lives in a non-scrolling input row, and closing is simpler than tracking
    // a stale rect through layout changes. Scrolls *inside* the popover's own
    // list are ignored so the user can reach items below the fold.
    useEffect(() => {
        if (!open) return;
        const onScroll = (e: Event) => {
            const target = e.target;
            if (target instanceof Node && popoverRef.current?.contains(target)) return;
            onClose();
        };
        const onResize = () => onClose();
        window.addEventListener("scroll", onScroll, true);
        window.addEventListener("resize", onResize);
        return () => {
            window.removeEventListener("scroll", onScroll, true);
            window.removeEventListener("resize", onResize);
        };
    }, [open, onClose]);

    if (!open) return null;
    if (typeof document === "undefined") return null;

    // Resolve the displayed checkbox state. When `selectedTools` is null
    // (default), every permitted tool renders checked — that mirrors
    // "the orchestrator will use them all." When the user toggles one
    // off, we materialize the selection to the remaining set so the
    // orchestrator narrows.
    const isChecked = (toolName: string): boolean => {
        if (selectedTools === null) return true;
        return selectedTools.includes(toolName);
    };

    const handleToggle = (toolName: string) => {
        // First narrowing toggle materializes the selection from "all"
        // to "all except this one".
        if (selectedTools === null) {
            const next = permittedTools
                .map(t => t.name)
                .filter(n => n !== toolName);
            onChange(next);
            return;
        }
        if (selectedTools.includes(toolName)) {
            onChange(selectedTools.filter(n => n !== toolName));
        } else {
            onChange([...selectedTools, toolName]);
        }
    };

    // Anchor to the trigger's top-right, 8px above it — matches the original
    // `bottom-full right-0 mb-2` visual. Clamp height to space above the
    // trigger so the list scrolls internally instead of running off-screen.
    // When no triggerRef is provided (e.g., in unit tests), render visible at
    // the default origin rather than masking the popover entirely.
    const awaitingRect = !!triggerRef && !rect;
    const popoverStyle: React.CSSProperties = {
        top: rect ? rect.top - 8 : 0,
        left: rect ? rect.right : 0,
        transform: rect ? "translate(-100%, -100%)" : undefined,
        maxHeight: rect ? Math.max(0, Math.min(384, rect.top - 16)) : 384,
        visibility: awaitingRect ? "hidden" : "visible",
    };

    return createPortal(
        <div
            ref={popoverRef}
            data-testid="tool-picker-popover"
            role="dialog"
            aria-label="Select agents and tools for this chat"
            style={popoverStyle}
            className="fixed w-80 overflow-y-auto bg-astral-surface border border-white/10 rounded-xl shadow-2xl z-50 p-2"
        >
            <div className="flex items-center justify-between px-2 py-1.5 border-b border-white/5 mb-1">
                <span className="text-xs font-medium text-white flex items-center gap-1.5">
                    <Wrench size={11} />
                    Tools &amp; Agents for this chat
                </span>
                <button
                    type="button"
                    onClick={onReset}
                    data-testid="tool-picker-reset"
                    title="Re-enable every agent and clear tool narrowing. The popover stays open so you can keep tweaking."
                    className="text-[10px] font-medium text-astral-muted hover:text-astral-primary flex items-center gap-1 transition-colors"
                >
                    <RotateCcw size={10} />
                    Reset all
                </button>
            </div>

            {/* Agents section — per-user agent on/off toggles. */}
            {agents.length > 0 && (
                <div className="mb-2" data-testid="tool-picker-agents-section">
                    <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-astral-muted/70 flex items-center gap-1">
                        <Bot size={10} />
                        Agents
                    </div>
                    <ul className="space-y-0.5">
                        {agents.map((agent) => {
                            const enabled = !agent.disabled;
                            return (
                                <li key={agent.id}>
                                    <button
                                        type="button"
                                        role="switch"
                                        aria-checked={enabled}
                                        aria-label={enabled ? `Disable ${agent.name}` : `Enable ${agent.name}`}
                                        data-testid={`tool-picker-agent-${agent.id}`}
                                        onClick={() => onAgentToggle?.(agent.id, !enabled)}
                                        title={enabled
                                            ? `${agent.name} is enabled — click to disable for this user.`
                                            : `${agent.name} is disabled — click to re-enable.`}
                                        className={`w-full flex items-center justify-between px-2 py-1.5 rounded-md transition-colors ${
                                            enabled
                                                ? "hover:bg-white/5"
                                                : "opacity-60 hover:bg-white/5"
                                        }`}
                                    >
                                        <span className="text-[11px] text-white truncate text-left flex-1 min-w-0" title={agent.name}>
                                            {agent.name}
                                        </span>
                                        <span
                                            className={`relative w-7 h-3.5 rounded-full transition-colors flex-shrink-0 ml-2 ${
                                                enabled ? "bg-astral-primary" : "bg-white/15"
                                            }`}
                                        >
                                            <span
                                                className={`absolute top-[1px] w-2.5 h-2.5 rounded-full bg-white transition-all ${
                                                    enabled ? "left-[14px]" : "left-[1px]"
                                                }`}
                                            />
                                        </span>
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </div>
            )}

            {/* Tools section header */}
            {agents.length > 0 && (
                <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-astral-muted/70 flex items-center gap-1 border-t border-white/5 pt-2">
                    <Wrench size={10} />
                    Tools
                </div>
            )}

            {permittedTools.length === 0 ? (
                <div className="px-2 py-3 text-[11px] text-astral-muted text-center">
                    {agents.length === 0
                        ? "No tools available."
                        : agents.every(a => a.disabled)
                            ? "All agents are disabled — re-enable one to see its tools."
                            : "No tools available for the enabled agents."}
                </div>
            ) : (
                <ul className="space-y-0.5" data-testid="tool-picker-list">
                    {permittedTools.map((tool) => {
                        const checked = isChecked(tool.name);
                        return (
                            <li key={tool.name}>
                                <label
                                    className="flex items-start gap-2 px-2 py-1.5 rounded-md hover:bg-white/5 cursor-pointer transition-colors"
                                    data-testid={`tool-picker-item-${tool.name}`}
                                >
                                    <span
                                        className={`mt-0.5 w-3.5 h-3.5 rounded-sm border flex items-center justify-center flex-shrink-0 transition-colors ${
                                            checked
                                                ? "bg-astral-primary border-astral-primary"
                                                : "bg-transparent border-white/20"
                                        }`}
                                    >
                                        {checked && <Check size={10} className="text-white" />}
                                    </span>
                                    <input
                                        type="checkbox"
                                        className="sr-only"
                                        checked={checked}
                                        onChange={() => handleToggle(tool.name)}
                                        aria-label={tool.name}
                                    />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1">
                                            <span className="text-[11px] text-white truncate" title={tool.name}>
                                                {tool.name}
                                            </span>
                                            {tool.description && (
                                                <span
                                                    className="text-astral-muted/50 hover:text-astral-primary transition-colors flex-shrink-0"
                                                    title={tool.description}
                                                    data-testid={`tool-picker-info-${tool.name}`}
                                                >
                                                    <Info size={10} />
                                                </span>
                                            )}
                                        </div>
                                        {tool.description && (
                                            <p className="text-[10px] text-astral-muted/60 line-clamp-2 mt-0.5">
                                                {tool.description}
                                            </p>
                                        )}
                                    </div>
                                </label>
                            </li>
                        );
                    })}
                </ul>
            )}
            {selectedTools !== null && selectedTools.length === 0 && (
                <div
                    data-testid="tool-picker-zero-warning"
                    className="mt-2 px-2 py-1.5 rounded-md bg-amber-400/10 border border-amber-400/30 text-[10px] text-amber-200"
                >
                    No tools selected — sending is disabled. Pick at least one tool or click Reset.
                </div>
            )}
        </div>,
        document.body,
    );
}
