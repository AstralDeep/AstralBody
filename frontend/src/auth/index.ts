/**
 * Public re-exports for the persistent-login (feature 016) auth helpers.
 *
 * Consumers should import from `frontend/src/auth` (this file), not
 * from the underlying module files directly.
 */

export {
    SafeWebStorageStateStore,
    PERSISTENCE_DISABLED_EVENT,
    type PersistenceDisabledDetail,
    type SafeWebStorageStateStoreOptions,
} from "./safeStorageStore";

export {
    ANCHOR_KEY,
    JUST_INTERACTIVE_KEY,
    HARD_MAX_MS,
    ANCHOR_SCHEMA_VERSION,
    RETRY_DELAYS_MS,
    getAnchor,
    clear,
    checkOnLaunch,
    recordInteractiveLogin,
    wasSilentResume,
    signOut,
    retryWithBackoff,
    reportSessionResumeFailed,
    type PersistentLoginAnchor,
    type CheckOnLaunchOutcome,
    type SessionResumeFailedReport,
} from "./persistentLogin";

export {
    QUEUE_KEY,
    REVOCATION_QUEUED_OFFLINE_EVENT,
    MAX_QUEUE_LENGTH,
    MAX_ATTEMPTS_PER_ENTRY,
    revocationQueue,
    attemptRevoke,
    initRevocationQueue,
    type RevocationEntry,
    type RevocationQueueApi,
} from "./revocationQueue";

export { oidcConfig } from "./oidcConfig";
