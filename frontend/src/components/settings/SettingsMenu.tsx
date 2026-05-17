/**
 * SettingsMenu — full-screen modal that consolidates the secondary
 * sidebar utility buttons (Audit log, LLM settings, Tool quality,
 * Tutorial admin, Take the tour, User guide) into a single grouped
 * menu (feature 007-sidebar-settings-menu).
 *
 * Renders one trigger button (gear icon) that opens a centered modal
 * conforming to the WAI-ARIA menu pattern (FR-012) inside a dialog:
 *   - aria-haspopup="menu" / aria-expanded toggling on the trigger
 *   - role="dialog" + aria-modal="true" on the card
 *   - role="menu" on the items container, role="menuitem" on each entry
 *   - Enter/Space on trigger opens menu and focuses the first item
 *   - Up/Down arrow keys, Home/End, Tab/Shift+Tab cycle within items
 *   - Escape closes the menu and restores focus to the trigger
 *   - Backdrop click closes (matches LlmSettingsPanel / AuditLogPanel)
 *
 * The modal pattern matches `frontend/src/components/llm/LlmSettingsPanel.tsx`
 * so the menu sits above all other UI regardless of stacking context
 * (the previous absolute-positioned popover could be obscured by
 * dynamic-rendered components in the chat area).
 *
 * Items are grouped into sections (Account / Help / Admin tools) per
 * research.md § Decision 4. When an open-callback prop is undefined,
 * the corresponding item is omitted; when every item in a group is
 * omitted, the group's heading is also hidden (FR-014). Admin items
 * render only when `isAdmin === true` (FR-005 / FR-006); admin
 * authorization is enforced server-side regardless (FR-015 — this
 * prop is UX-only).
 *
 * Tutorial integration (FR-010): when the active tutorial step's
 * target_key matches one of the menu's items (e.g., `sidebar.audit`),
 * the menu auto-opens so the spotlight can highlight the target.
 * When the target_key transitions away (off-menu key or null), the
 * menu auto-closes so it doesn't obscure subsequent targets.
 *
 * No third-party dropdown / dialog library — Constitution Principle V / FR-013.
 */
import {
    useCallback,
    useEffect,
    useId,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent as ReactKeyboardEvent,
    type ReactElement,
} from "react";
import { createPortal } from "react-dom";
import { Settings, X } from "lucide-react";

import { useOnboarding } from "../onboarding/OnboardingContext";

export interface SettingsMenuProps {
    /**
     * Whether the signed-in user has the admin role. UX-ONLY: even
     * when false, server-side authorization is what actually keeps
     * non-admins out of admin endpoints (FR-015). Defaults to false.
     */
    isAdmin?: boolean;
    onOpenAuditLog?: () => void;
    onOpenLlmSettings?: () => void;
    onOpenFeedbackAdmin?: () => void;
    onOpenTutorialAdmin?: () => void;
    onReplayTutorial?: () => void;
    onOpenUserGuide?: () => void;
    /**
     * Optional pending-flags count for the admin "Tool quality" item.
     * When > 0 and the Tool quality item is rendered, the menuitem
     * shows a red badge ("N flagged") so admins see the queue depth
     * at a glance — preserves the affordance the original
     * sidebar-button shipped in feature 004.
     */
    flaggedToolsCount?: number;
    /**
     * Trigger appearance:
     *   - "expanded" (default): icon + "Settings" label, full width.
     *     Used inside the expanded sidebar and the mobile drawer.
     *   - "collapsed": gear-only icon button. Used in the desktop
     *     icon rail (sidebar collapsed).
     */
    variant?: "expanded" | "collapsed";
    /** Optional className appended to the root wrapper. */
    className?: string;
    /**
     * Fires whenever the menu's open state changes. Used by the
     * dashboard to auto-collapse the mobile sidebar so the modal
     * isn't visually hidden behind it.
     */
    onOpenChange?: (open: boolean) => void;
}

interface MenuItem {
    key: string;
    label: string;
    onSelect: () => void;
    /** Optional inline badge text, e.g. "3 flagged". */
    badge?: string;
    /** Variant of the badge — "alert" → red, "muted" → grey. */
    badgeVariant?: "alert" | "muted";
}

interface MenuSection {
    label: string;
    items: MenuItem[];
}

/**
 * Tutorial target keys whose active step should auto-open this menu
 * because their visual target now lives inside the popover. Keep in
 * sync with the `data-tutorial-target` values rendered below.
 */
const TUTORIAL_TARGET_KEYS: ReadonlySet<string> = new Set([
    "sidebar.audit",
    "sidebar.llm",
    "sidebar.replay-tour",
    "sidebar.user-guide",
    "sidebar.feedback-admin",
    "sidebar.tutorial-admin",
]);

export function SettingsMenu(props: SettingsMenuProps): ReactElement {
    const {
        isAdmin = false,
        onOpenAuditLog,
        onOpenLlmSettings,
        onOpenFeedbackAdmin,
        onOpenTutorialAdmin,
        onReplayTutorial,
        onOpenUserGuide,
        flaggedToolsCount,
        variant = "expanded",
        className,
        onOpenChange,
    } = props;

    const [open, setOpen] = useState<boolean>(false);
    const [focusedIndex, setFocusedIndex] = useState<number>(-1);
    const triggerRef = useRef<HTMLButtonElement | null>(null);
    const popoverRef = useRef<HTMLDivElement | null>(null);
    const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
    const menuId = useId();
    const dialogTitleId = useId();

    // -----------------------------------------------------------------
    // Build the (sectioned, omission-aware) item list. FR-014.
    // -----------------------------------------------------------------
    const sections = useMemo<MenuSection[]>(() => {
        const account: MenuItem[] = [];
        if (onOpenAuditLog) {
            account.push({ key: "sidebar.audit", label: "Audit log", onSelect: onOpenAuditLog });
        }
        if (onOpenLlmSettings) {
            account.push({ key: "sidebar.llm", label: "LLM settings", onSelect: onOpenLlmSettings });
        }

        const help: MenuItem[] = [];
        if (onReplayTutorial) {
            help.push({ key: "sidebar.replay-tour", label: "Take the tour", onSelect: onReplayTutorial });
        }
        if (onOpenUserGuide) {
            help.push({ key: "sidebar.user-guide", label: "User guide", onSelect: onOpenUserGuide });
        }

        const admin: MenuItem[] = [];
        if (isAdmin) {
            if (onOpenFeedbackAdmin) {
                const count = flaggedToolsCount ?? 0;
                admin.push({
                    key: "sidebar.feedback-admin",
                    label: "Tool quality",
                    onSelect: onOpenFeedbackAdmin,
                    badge: count > 0 ? `${count > 99 ? "99+" : count} flagged` : undefined,
                    badgeVariant: count > 0 ? "alert" : undefined,
                });
            }
            if (onOpenTutorialAdmin) {
                admin.push({ key: "sidebar.tutorial-admin", label: "Tutorial admin", onSelect: onOpenTutorialAdmin });
            }
        }

        const out: MenuSection[] = [];
        if (account.length > 0) out.push({ label: "Account", items: account });
        if (help.length > 0) out.push({ label: "Help", items: help });
        if (admin.length > 0) out.push({ label: "Admin tools", items: admin });
        return out;
    }, [
        isAdmin,
        onOpenAuditLog,
        onOpenLlmSettings,
        onOpenFeedbackAdmin,
        onOpenTutorialAdmin,
        onReplayTutorial,
        onOpenUserGuide,
        flaggedToolsCount,
    ]);

    const flatItems = useMemo<MenuItem[]>(
        () => sections.flatMap((s) => s.items),
        [sections],
    );

    // Reset stale ref slots when the items array shrinks (admin gating change, etc.).
    if (itemRefs.current.length !== flatItems.length) {
        itemRefs.current = new Array(flatItems.length).fill(null);
    }

    // -----------------------------------------------------------------
    // Tutorial auto-open / auto-close. FR-010.
    // -----------------------------------------------------------------
    const onboarding = useOnboarding();
    const targetKey: string | null = onboarding?.currentStepTargetKey ?? null;
    useEffect(() => {
        if (targetKey && TUTORIAL_TARGET_KEYS.has(targetKey)) {
            setOpen(true);
            // Don't steal focus from the tutorial overlay's spotlight.
            setFocusedIndex(-1);
        } else {
            setOpen(false);
            setFocusedIndex(-1);
        }
    }, [targetKey]);

    // -----------------------------------------------------------------
    // Click-outside dismiss + global Escape. FR-008.
    // -----------------------------------------------------------------
    useEffect(() => {
        if (!open) return;
        const onDocClick = (ev: MouseEvent) => {
            const t = ev.target as Node | null;
            if (!t) return;
            if (popoverRef.current && popoverRef.current.contains(t)) return;
            if (triggerRef.current && triggerRef.current.contains(t)) return;
            setOpen(false);
            setFocusedIndex(-1);
        };
        const onDocKeyDown = (ev: KeyboardEvent) => {
            // Catch Escape regardless of where focus lives — the
            // popover-level handler only fires when focus is inside
            // the menu, but the menu can be mouse-opened with focus
            // remaining on the trigger.
            if (ev.key === "Escape") {
                ev.preventDefault();
                setOpen(false);
                setFocusedIndex(-1);
                triggerRef.current?.focus();
            }
        };
        // Defer attach by one tick so the click that opened us doesn't
        // close us immediately.
        const handle = window.setTimeout(() => {
            document.addEventListener("click", onDocClick);
        }, 0);
        document.addEventListener("keydown", onDocKeyDown);
        return () => {
            window.clearTimeout(handle);
            document.removeEventListener("click", onDocClick);
            document.removeEventListener("keydown", onDocKeyDown);
        };
    }, [open]);

    // -----------------------------------------------------------------
    // Move DOM focus to follow `focusedIndex` when the menu is open.
    // -----------------------------------------------------------------
    useEffect(() => {
        if (!open) return;
        if (focusedIndex < 0 || focusedIndex >= flatItems.length) return;
        const el = itemRefs.current[focusedIndex];
        if (el) el.focus();
    }, [open, focusedIndex, flatItems.length]);

    useEffect(() => {
        onOpenChange?.(open);
    }, [open, onOpenChange]);

    const closeAndRestoreFocus = useCallback(() => {
        setOpen(false);
        setFocusedIndex(-1);
        // Synchronously refocus the trigger; setOpen(false) re-renders
        // and unmounts the popover, but the trigger element is stable.
        triggerRef.current?.focus();
    }, []);

    const activate = useCallback(
        (item: MenuItem) => {
            try {
                item.onSelect();
            } finally {
                closeAndRestoreFocus();
            }
        },
        [closeAndRestoreFocus],
    );

    // -----------------------------------------------------------------
    // Trigger keyboard: Enter/Space opens menu and focuses first item.
    // -----------------------------------------------------------------
    const onTriggerKeyDown = useCallback(
        (ev: ReactKeyboardEvent<HTMLButtonElement>) => {
            if (ev.key === "Enter" || ev.key === " " || ev.key === "Spacebar") {
                ev.preventDefault();
                setOpen(true);
                setFocusedIndex(0);
            }
        },
        [],
    );

    const onTriggerClick = useCallback(() => {
        setOpen((prev) => {
            if (prev) {
                setFocusedIndex(-1);
                return false;
            }
            // Mouse-open: don't auto-grab focus on first item (matches
            // the convention that pointer interaction doesn't yank
            // keyboard focus). Tests for keyboard nav use Enter on
            // trigger which goes through onTriggerKeyDown above.
            return true;
        });
    }, []);

    // -----------------------------------------------------------------
    // Menu keyboard: arrow / home / end / tab / enter / space / esc.
    // -----------------------------------------------------------------
    const onMenuKeyDown = useCallback(
        (ev: ReactKeyboardEvent<HTMLDivElement>) => {
            if (!open) return;
            const count = flatItems.length;
            if (count === 0) return;
            switch (ev.key) {
                case "Escape":
                    ev.preventDefault();
                    closeAndRestoreFocus();
                    break;
                case "ArrowDown":
                    ev.preventDefault();
                    setFocusedIndex((i) => (i + 1 + count) % count);
                    break;
                case "ArrowUp":
                    ev.preventDefault();
                    setFocusedIndex((i) => (i <= 0 ? count - 1 : i - 1));
                    break;
                case "Home":
                    ev.preventDefault();
                    setFocusedIndex(0);
                    break;
                case "End":
                    ev.preventDefault();
                    setFocusedIndex(count - 1);
                    break;
                case "Tab":
                    // Trap Tab inside menu items (FR-012).
                    ev.preventDefault();
                    if (ev.shiftKey) {
                        setFocusedIndex((i) => (i <= 0 ? count - 1 : i - 1));
                    } else {
                        setFocusedIndex((i) => (i + 1 + count) % count);
                    }
                    break;
                case "Enter":
                case " ":
                case "Spacebar": {
                    if (focusedIndex >= 0 && focusedIndex < count) {
                        ev.preventDefault();
                        activate(flatItems[focusedIndex]);
                    }
                    break;
                }
                default:
                    break;
            }
        },
        [open, flatItems, focusedIndex, activate, closeAndRestoreFocus],
    );

    // -----------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------
    const isCollapsed = variant === "collapsed";
    const triggerClass = isCollapsed
        ? "p-2.5 rounded-lg hover:bg-white/10 transition-colors"
        : "w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-white/5 transition-colors group text-left";
    const wrapperClass = `settings-menu ${className ?? ""}`.trim();

    return (
        <div className={wrapperClass}>
            <button
                ref={triggerRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={menuId}
                aria-label="Settings"
                onClick={onTriggerClick}
                onKeyDown={onTriggerKeyDown}
                className={triggerClass}
                title={isCollapsed ? "Settings" : undefined}
                data-tutorial-target="sidebar.settings"
            >
                {isCollapsed ? (
                    <Settings size={18} className="text-astral-primary" />
                ) : (
                    <>
                        <div className="w-6 h-6 rounded-md bg-astral-primary/20 flex items-center justify-center flex-shrink-0">
                            <Settings size={12} className="text-astral-primary" />
                        </div>
                        <span className="text-xs font-medium text-white flex-1">Settings</span>
                    </>
                )}
            </button>

            {open && flatItems.length > 0 && typeof document !== "undefined" && createPortal(
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                    onClick={closeAndRestoreFocus}
                >
                    <div
                        ref={popoverRef}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby={dialogTitleId}
                        onClick={(e) => e.stopPropagation()}
                        className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-sm mx-4 max-h-[90vh] flex flex-col"
                    >
                        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                                    <Settings size={16} className="text-astral-primary" />
                                </div>
                                <h2 id={dialogTitleId} className="text-sm font-semibold text-white">
                                    Settings
                                </h2>
                            </div>
                            <button
                                type="button"
                                onClick={closeAndRestoreFocus}
                                className="p-1.5 rounded-lg hover:bg-white/10"
                                aria-label="Close"
                            >
                                <X size={14} className="text-astral-muted" />
                            </button>
                        </div>

                        <div
                            id={menuId}
                            role="menu"
                            aria-label="Settings"
                            aria-orientation="vertical"
                            onKeyDown={onMenuKeyDown}
                            className="flex-1 overflow-y-auto py-2"
                        >
                            {sections.map((section, sIdx) => {
                                const startIdx = sections
                                    .slice(0, sIdx)
                                    .reduce((sum, s) => sum + s.items.length, 0);
                                const sectionId = `${menuId}-section-${sIdx}`;
                                return (
                                    <div
                                        key={section.label}
                                        role="group"
                                        aria-labelledby={sectionId}
                                        className="settings-menu-group py-1"
                                    >
                                        <div
                                            id={sectionId}
                                            className="px-6 pt-1 pb-1 text-[10px] font-semibold uppercase tracking-widest text-astral-muted select-none"
                                        >
                                            {section.label}
                                        </div>
                                        {section.items.map((item, idxInSection) => {
                                            const flatIdx = startIdx + idxInSection;
                                            const badgeClass =
                                                item.badgeVariant === "alert"
                                                    ? "text-[10px] font-bold text-red-400 ml-2 flex-shrink-0"
                                                    : "text-[10px] text-astral-muted ml-2 flex-shrink-0";
                                            return (
                                                <button
                                                    key={item.key}
                                                    ref={(el) => {
                                                        itemRefs.current[flatIdx] = el;
                                                    }}
                                                    type="button"
                                                    role="menuitem"
                                                    tabIndex={focusedIndex === flatIdx ? 0 : -1}
                                                    data-tutorial-target={item.key}
                                                    onClick={() => activate(item)}
                                                    className="w-full flex items-center px-6 py-2 text-xs text-white hover:bg-white/5 focus:bg-white/5 outline-none text-left"
                                                >
                                                    <span className="flex-1 truncate">{item.label}</span>
                                                    {item.badge && (
                                                        <span className={badgeClass} aria-label={item.badge}>
                                                            {item.badge}
                                                        </span>
                                                    )}
                                                </button>
                                            );
                                        })}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </div>
    );
}

export default SettingsMenu;
