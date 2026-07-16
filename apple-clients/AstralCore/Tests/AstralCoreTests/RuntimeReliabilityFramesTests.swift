import XCTest

@testable import AstralCore

final class RuntimeReliabilityFramesTests: XCTestCase {
    private let chatId = "11111111-1111-4111-8111-111111111111"
    private let connection = "22222222-2222-4222-8222-222222222222"
    private let request = "33333333-3333-4333-8333-333333333333"

    private func frame(_ json: String) throws -> InboundFrame {
        try XCTUnwrap(InboundFrame.parse(json))
    }

    func testConversationSnapshotRequiresEveryCanonicalField() throws {
        let value = try frame(
            """
            {
              "type":"conversation_snapshot",
              "schema_version":1,
              "snapshot_id":"44444444-4444-4444-8444-444444444444",
              "chat_id":"\(chatId)",
              "connection_generation":"\(connection)",
              "request_generation":"\(request)",
              "snapshot_purpose":"hydration",
              "render_revision":7,
              "committed_at":"2026-07-15T18:41:00Z",
              "transcript":[],
              "canvas":{"target":"canvas","components":[]}
            }
            """)
        let snapshot = try XCTUnwrap(ConversationSnapshot(frame: value))

        XCTAssertEqual(snapshot.snapshotPurpose, "hydration")
        XCTAssertEqual(snapshot.renderRevision, 7)
        XCTAssertEqual(snapshot.transcript, [])

        let malformed = try frame(
            """
            {"type":"conversation_snapshot","schema_version":1,
             "snapshot_id":"44444444-4444-4444-8444-444444444444",
             "chat_id":"\(chatId)","connection_generation":"\(connection)",
             "request_generation":"\(request)","snapshot_purpose":"preview",
             "render_revision":7,"committed_at":"2026-07-15T18:41:00Z",
             "transcript":[],"canvas":{"target":"canvas","components":[]}}
            """)
        XCTAssertNil(ConversationSnapshot(frame: malformed))
    }

    func testOperationStatusAndLifecycleValidateFlagsAndGenerations() throws {
        let statusFrame = try frame(
            """
            {"type":"operation_status",
             "operation_id":"55555555-5555-4555-8555-555555555555",
             "action":"chrome_llm_save","surface":"llm_settings","chat_id":null,
             "connection_generation":"\(connection)","request_generation":"\(request)",
             "sequence":2,"state":"validating","phase":"validating_credentials",
             "label":"Checking credentials","terminal":false,"retryable":false,
             "error":null,"retry_after_ms":null,"updated_at":"2026-07-15T18:41:00Z"}
            """)
        let lifecycleFrame = try frame(
            """
            {"type":"agent_lifecycle","agent_id":"ua-dice-4f3c2a",
             "revision_id":"66666666-6666-4666-8666-666666666666",
             "runtime_instance_id":"77777777-7777-4777-8777-777777777777",
             "lifecycle_generation":14,"state_revision":3,"state":"online",
             "reason_code":null,"label":"Online","updated_at":"2026-07-15T18:41:00Z"}
            """)

        XCTAssertEqual(OperationStatus(frame: statusFrame)?.state, "validating")
        let lifecycle = try XCTUnwrap(AgentLifecycle(frame: lifecycleFrame))
        XCTAssertEqual(lifecycle.lifecycleGeneration, 14)
        XCTAssertEqual(lifecycle.stateRevision, 3)

        let invalidStatus = try frame(
            """
            {"type":"operation_status",
             "operation_id":"55555555-5555-4555-8555-555555555555",
             "action":"chrome_llm_save","surface":"llm_settings","chat_id":null,
             "connection_generation":"\(connection)","request_generation":"\(request)",
             "sequence":2,"state":"completed","phase":"completed",
             "label":"Done","terminal":false,"retryable":false,
             "error":null,"retry_after_ms":null,"updated_at":"2026-07-15T18:41:00Z"}
            """)
        XCTAssertNil(OperationStatus(frame: invalidStatus))

        let unknownErrorCode = try frame(
            """
            {"type":"operation_status",
             "operation_id":"55555555-5555-4555-8555-555555555555",
             "action":"chrome_llm_save","surface":"llm_settings","chat_id":null,
             "connection_generation":"\(connection)","request_generation":"\(request)",
             "sequence":3,"state":"failed","phase":"failed",
             "label":"Failed","terminal":true,"retryable":false,
             "error":{"code":"internal_trace","message":"Safe"},
             "retry_after_ms":null,"updated_at":"2026-07-15T18:41:00Z"}
            """)
        XCTAssertNil(OperationStatus(frame: unknownErrorCode))

        let activeWithoutRuntime = try frame(
            """
            {"type":"agent_lifecycle","agent_id":"ua-dice-4f3c2a",
             "revision_id":"66666666-6666-4666-8666-666666666666",
             "runtime_instance_id":null,"lifecycle_generation":14,
             "state_revision":4,"state":"online","reason_code":null,
             "label":"Online","updated_at":"2026-07-15T18:41:00Z"}
            """)
        XCTAssertNil(AgentLifecycle(frame: activeWithoutRuntime))

        let unknownReason = try frame(
            """
            {"type":"agent_lifecycle","agent_id":"ua-dice-4f3c2a",
             "revision_id":"66666666-6666-4666-8666-666666666666",
             "runtime_instance_id":null,"lifecycle_generation":14,
             "state_revision":5,"state":"offline","reason_code":"raw_child_trace",
             "label":"Offline","updated_at":"2026-07-15T18:41:00Z"}
            """)
        XCTAssertNil(AgentLifecycle(frame: unknownReason))
    }

    func testEveryUIEventDuplicatesCanonicalClientOperationIdentities() throws {
        let submission = "88888888-8888-4888-8888-888888888888"
        let requestGeneration = "99999999-9999-4999-8999-999999999999"
        let payload = try JSONValue.parse(
            Data(
                Outbound.uiEvent(
                    action: "chrome_open",
                    sessionId: nil,
                    payload: .object(["surface": .string("llm_settings")]),
                    submissionId: submission,
                    requestGeneration: requestGeneration
                ).utf8))

        XCTAssertEqual(payload["submission_id"]?.stringValue, submission)
        XCTAssertEqual(payload["request_generation"]?.stringValue, requestGeneration)
        XCTAssertEqual(payload["payload"]?["submission_id"]?.stringValue, submission)
        XCTAssertEqual(
            payload["payload"]?["request_generation"]?.stringValue,
            requestGeneration)

        let updateDevice = try JSONValue.parse(
            Data(
                Outbound.updateDevice(
                    sessionId: nil,
                    device: .ios(viewportWidth: 390, viewportHeight: 844),
                    submissionId: submission,
                    requestGeneration: requestGeneration
                ).utf8))
        XCTAssertEqual(updateDevice["submission_id"]?.stringValue, submission)
        XCTAssertEqual(
            updateDevice["payload"]?["submission_id"]?.stringValue,
            submission)
        XCTAssertEqual(
            updateDevice["payload"]?["request_generation"]?.stringValue,
            requestGeneration)
        XCTAssertNotNil(updateDevice["payload"]?["device"]?.objectValue)

        let refusal = try frame(
            """
            {"type":"error","submission_id":"\(submission)","accepted":false,
             "code":"capacity_exceeded","message":"Try again.","retryable":true,
             "retry_after_ms":500}
            """)
        XCTAssertEqual(AdmissionRefusal(frame: refusal)?.submissionId, submission)

        for invalidId in [
            "null",
            "\"AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA\"",
            "\"not-a-uuid\"",
        ] {
            let invalid = try frame(
                """
                {"type":"error","submission_id":\(invalidId),"accepted":false,
                 "code":"capacity_exceeded","message":"Try again.","retryable":true,
                 "retry_after_ms":500}
                """)
            XCTAssertNil(AdmissionRefusal(frame: invalid))
        }
    }

    func testAppleRegistrationIsExplicitlyAuthorOnlyAndAckIsModeled() throws {
        let registration = try XCTUnwrap(
            AgentHostRegistration(
                hostId: "88888888-8888-4888-8888-888888888888",
                supportedRuntimeContractVersions: [2],
                runtimeLockSHA256: String(repeating: "ab", count: 32),
                platform: "macos",
                clientVersion: "0.4.0"
            ))
        XCTAssertEqual(
            registration.json["supported_runtime_contract_versions"]?.arrayValue?.count,
            1
        )

        let outbound = Outbound.registerUI(
            token: "token",
            sessionId: nil,
            device: .macos(viewportWidth: 800, viewportHeight: 600),
            resumed: false
        )
        let outboundJSON = try JSONValue.parse(try XCTUnwrap(outbound.data(using: .utf8)))
        XCTAssertNil(outboundJSON["agent_host"])
        XCTAssertFalse(
            outboundJSON["capabilities"]?.arrayValue?.contains(.string("agent_host")) ?? true
        )

        let acknowledgement = try frame(
            """
            {"type":"agent_host_registered",
             "host_id":"88888888-8888-4888-8888-888888888888",
             "host_session_id":"99999999-9999-4999-8999-999999999999",
             "inventory_required":true,"accepted_at":"2026-07-15T18:41:00Z"}
            """)
        XCTAssertEqual(
            AgentHostRegistered(frame: acknowledgement)?.hostSessionId,
            "99999999-9999-4999-8999-999999999999"
        )
        for client in [ClientDispositions.ios, .macos, .watch] {
            guard case .ignored = client.frames["agent_host_registered"] else {
                return XCTFail("\(client.client) must remain author-only")
            }
        }
    }

    func testCandidateCapabilityMapRejectsMissingOrMalformedApplicability() throws {
        let unsupported = try JSONValue.parse(
            Data(
                """
                {"capabilities":{"personal_agent_host":{"macos":{
                  "supported":false,"runtime_contract_versions":[],"source_feature":null
                }}}}
                """.utf8))
        let supported = try JSONValue.parse(
            Data(
                """
                {"capabilities":{"personal_agent_host":{"macos":{
                  "supported":true,"runtime_contract_versions":[2],"source_feature":"059"
                }}}}
                """.utf8))
        let malformed = try JSONValue.parse(
            Data(
                """
                {"capabilities":{"personal_agent_host":{"macos":{
                  "supported":false,"runtime_contract_versions":[2],"source_feature":null
                }}}}
                """.utf8))

        XCTAssertEqual(
            CandidateCapabilityMap(json: unsupported)?.macOSPersonalAgentHost.supported,
            false
        )
        XCTAssertEqual(
            CandidateCapabilityMap(json: supported)?.macOSPersonalAgentHost.sourceFeature,
            "059"
        )
        XCTAssertNil(CandidateCapabilityMap(json: malformed))
        XCTAssertNil(CandidateCapabilityMap(json: .object(["capabilities": .object([:])])))
    }
}
