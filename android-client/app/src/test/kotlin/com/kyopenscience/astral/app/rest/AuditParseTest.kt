package com.kyopenscience.astral.app.rest

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AuditParseTest {
    @Test
    fun parses_top_level_array() {
        val raw = """[{"id":"e1","event_class":"auth","action":"login","outcome":"success","recorded_at":"2026-06-30"}]"""
        val events = parseAudit(raw)
        assertEquals(1, events.size)
        assertEquals("e1", events[0].id)
        assertEquals("auth", events[0].eventClass)
        assertEquals("login", events[0].action)
        assertEquals("success", events[0].outcome)
    }

    @Test
    fun parses_object_wrapped_under_events() {
        val raw = """{"events":[{"id":"a","action":"x"},{"id":"b","action":"y"}]}"""
        val events = parseAudit(raw)
        assertEquals(listOf("a", "b"), events.map { it.id })
    }

    @Test
    fun tolerates_alt_field_spellings() {
        val raw = """[{"event_id":"z","class":"tool","result":"failure","timestamp":"t"}]"""
        val e = parseAudit(raw).single()
        assertEquals("z", e.id)
        assertEquals("tool", e.eventClass)
        assertEquals("failure", e.outcome)
        assertEquals("t", e.recordedAt)
    }

    @Test
    fun empty_or_garbage_yields_empty_list() {
        assertTrue(parseAudit("").isEmpty())
        assertTrue(parseAudit("not json").isEmpty())
        assertTrue(parseAudit("""{"unexpected":true}""").isEmpty())
    }
}
