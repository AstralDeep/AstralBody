/**
 * Ambient progress indicator for in-flight chat turns
 * (feature 014-progress-notifications, US1).
 *
 * Renders a single rotating cosmic-themed word inside the chat's loading slot.
 * Purely client-side: the word is never named by the backend. See
 * specs/014-progress-notifications/contracts/chat_status_extension.md.
 *
 * Behaviour summary:
 *  - Visible while {@link ChatStatus.status} is in-flight (`thinking` /
 *    `executing` / `fixing`); otherwise unmounted.
 *  - The displayed word rotates every {@link ROTATION_INTERVAL_MS}ms, and never
 *    repeats two in a row (R7 anti-stutter).
 *  - The interval is cleared on unmount and on transition to a non-in-flight
 *    status.
 */
import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import type { ChatStatus } from "../../hooks/useWebSocket";
import { pickCosmicWord } from "./chatStepWords";

/**
 * Rotation cadence chosen in research R7.
 *
 * 1.2 s clears SC-002's 1-per-second floor without crossing the 3 s ceiling
 * and is fast enough to feel alive without being noisy.
 */
const ROTATION_INTERVAL_MS = 1200;

const IN_FLIGHT_STATUSES: ReadonlyArray<string> = ["thinking", "executing", "fixing"];

interface CosmicProgressIndicatorProps {
    chatStatus: ChatStatus;
}

/**
 * Renders the rotating cosmic-word progress indicator while a turn is in
 * flight. Returns `null` when the turn is idle/done so it can be dropped
 * straight into a parent's loading slot without further conditional logic.
 */
export function CosmicProgressIndicator({ chatStatus }: CosmicProgressIndicatorProps) {
    const isInFlight = IN_FLIGHT_STATUSES.includes(chatStatus.status);
    const [word, setWord] = useState<string>(() => pickCosmicWord());

    useEffect(() => {
        if (!isInFlight) {
            return undefined;
        }
        const timer = window.setInterval(() => {
            setWord((prev) => pickCosmicWord(prev));
        }, ROTATION_INTERVAL_MS);

        return () => {
            window.clearInterval(timer);
        };
    }, [isInFlight]);

    if (!isInFlight) {
        return null;
    }

    return (
        <span
            data-testid="cosmic-progress-indicator"
            aria-live="polite"
            aria-atomic="true"
            className="inline-flex items-center"
        >
            <motion.span
                key={word}
                data-testid="cosmic-progress-word"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="text-xs text-astral-muted"
            >
                {word}…
            </motion.span>
        </span>
    );
}
