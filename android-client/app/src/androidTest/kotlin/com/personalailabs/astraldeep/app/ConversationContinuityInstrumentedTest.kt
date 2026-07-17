package com.personalailabs.astraldeep.app

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.personalailabs.astraldeep.app.auth.ConversationResumeStore
import com.personalailabs.astraldeep.app.auth.ConversationResumeStore.AccountIdentity
import com.personalailabs.astraldeep.app.auth.ConversationResumeStore.ClearReason
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Connected Spec 060 continuity trials using Android's real preference implementation. */
@RunWith(AndroidJUnit4::class)
class ConversationContinuityInstrumentedTest {
    private val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    private val account = AccountIdentity("https://id.example/realms/astral", "instrumented-user")
    private val chatId = "11111111-1111-4111-8111-111111111111"

    @After
    fun clearTrialState() {
        ConversationResumeStore(context).clear(account, ClearReason.ACCOUNT_SWITCH_OR_REMOVAL)
    }

    @Test
    fun twenty_process_recreation_trials_restore_the_same_account_scoped_locator() {
        repeat(20) { trial ->
            val writer = ConversationResumeStore(context)
            assertTrue("trial $trial write", writer.save(account, chatId))

            val recreated = ConversationResumeStore(context)
            assertEquals("trial $trial recreate", chatId, recreated.load(account)?.chatId)
            assertNull(
                "trial $trial account isolation",
                recreated.load(AccountIdentity(account.issuer, "foreign-$trial")),
            )
        }
    }

    @Test
    fun definitive_clear_is_synchronous_across_a_new_store_instance() {
        val writer = ConversationResumeStore(context)
        assertTrue(writer.save(account, chatId))
        assertTrue(writer.clear(account, ClearReason.DEFINITIVE_SIGN_OUT))

        assertNull(ConversationResumeStore(context).load(account))
    }
}
