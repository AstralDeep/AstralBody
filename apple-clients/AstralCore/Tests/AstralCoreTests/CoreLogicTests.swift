// Feature 051 — PKCE (RFC 7636 test vector), the shared reconnect contract
// (backoff + bounded queue, FR-005), and lenient frame decoding (FR-003).
import XCTest

@testable import AstralCore

final class PKCETests: XCTestCase {
    func testRFC7636AppendixBVector() {
        // RFC 7636 Appendix B: the canonical S256 example.
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        XCTAssertEqual(
            PKCE.challenge(for: verifier),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    }

    func testVerifierShapeAndUniqueness() {
        let a = PKCE.makeVerifier()
        let b = PKCE.makeVerifier()
        XCTAssertNotEqual(a, b)
        XCTAssertEqual(a.count, 43)  // 32 octets, base64url, no padding
        XCTAssertFalse(a.contains("=") || a.contains("+") || a.contains("/"))
    }

    func testAuthorizeURLCarriesPKCE() {
        let config = OIDCConfig(
            authority: URL(string: "https://idp.example/realms/astral")!,
            clientId: "astral-mobile",
            redirectURI: "astraldeep://oauth2redirect")
        let url = config.authorizeURL(state: "st", challenge: "ch")
        let query = URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!
        func value(_ name: String) -> String? {
            query.first { $0.name == name }?.value
        }
        XCTAssertEqual(value("code_challenge_method"), "S256")
        XCTAssertEqual(value("code_challenge"), "ch")
        XCTAssertEqual(value("client_id"), "astral-mobile")
        XCTAssertEqual(value("response_type"), "code")
    }
}

final class ReconnectContractTests: XCTestCase {
    func testBackoffLadderMatchesSharedContract() {
        var policy = BackoffPolicy()
        XCTAssertEqual(policy.next(), 1)
        XCTAssertEqual(policy.next(), 2)
        XCTAssertEqual(policy.next(), 4)
        XCTAssertEqual(policy.next(), 8)
        XCTAssertEqual(policy.next(), 16)
        XCTAssertEqual(policy.next(), 30)  // capped
        XCTAssertEqual(policy.next(), 30)
        policy.reset()
        XCTAssertEqual(policy.next(), 1)  // reset on success
    }

    func testBoundedQueueDropsOldestAt64() {
        var queue = BoundedQueue<Int>(limit: 64)
        for i in 0..<64 {
            XCTAssertFalse(queue.append(i))
        }
        XCTAssertTrue(queue.append(64))  // drop signal
        XCTAssertEqual(queue.droppedCount, 1)
        let drained = queue.drainAll()
        XCTAssertEqual(drained.count, 64)
        XCTAssertEqual(drained.first, 1)  // FIFO, oldest dropped
        XCTAssertEqual(drained.last, 64)
        XCTAssertEqual(queue.count, 0)
    }
}

final class JSONValueParseTests: XCTestCase {
    /// The JSONSerialization fast path must keep the Codable route's
    /// semantics — booleans stay booleans (CFBoolean is an NSNumber), numbers
    /// stay numbers, and every JSON shape round-trips through `encoded()`.
    func testScalarKindsSurviveParse() throws {
        let json = try JSONValue.parse(
            Data(
                #"{"b":true,"f":false,"one":1,"pi":3.5,"zero":0,"s":"1","n":null}"#.utf8))
        XCTAssertEqual(json["b"], .bool(true))
        XCTAssertEqual(json["f"], .bool(false))
        XCTAssertEqual(json["one"], .number(1))
        XCTAssertEqual(json["pi"], .number(3.5))
        XCTAssertEqual(json["zero"], .number(0))  // NOT .bool(false)
        XCTAssertEqual(json["s"], .string("1"))  // NOT .number(1)
        XCTAssertEqual(json["n"], .null)
    }

    func testNestedTreesAndFragments() throws {
        let nested = try JSONValue.parse(Data(#"{"a":[{"x":[1,true,"y",null]}]}"#.utf8))
        XCTAssertEqual(
            nested["a"]?.arrayValue?.first?["x"],
            .array([.number(1), .bool(true), .string("y"), .null]))
        // Top-level fragments parse (JSONDecoder parity).
        XCTAssertEqual(try JSONValue.parse(Data("[1,2]".utf8)), .array([.number(1), .number(2)]))
        XCTAssertEqual(try JSONValue.parse(Data(#""hi""#.utf8)), .string("hi"))
        XCTAssertEqual(try JSONValue.parse(Data("true".utf8)), .bool(true))
        XCTAssertThrowsError(try JSONValue.parse(Data("not json".utf8)))
    }

    func testEncodedRoundTrip() throws {
        let original: JSONValue = .object([
            "list": .array([.bool(true), .number(2.5), .string("x")]),
            "empty": .object([:]),
            "gap": .null,
        ])
        XCTAssertEqual(try JSONValue.parse(original.encoded()), original)
    }
}

final class FrameDecodeTests: XCTestCase {
    func testUnknownFrameIsSafelyRepresented() {
        let frame = InboundFrame.parse(#"{"type":"frame_from_the_future","x":1}"#)
        XCTAssertEqual(frame?.name, "frame_from_the_future")
    }

    func testGarbageIsNil() {
        XCTAssertNil(InboundFrame.parse("not json"))
        XCTAssertNil(InboundFrame.parse(#"{"no_type":true}"#))
    }

    func testUIRenderWithSpeech() throws {
        let text = """
            {"type":"ui_render","target":"canvas",
             "components":[{"type":"text","content":"72 and clear"},
                           {"type":"metric","title":"Temp","value":"72"}],
             "speech":{"ssml":"<speak><s>72 and clear</s></speak>","text":"72 and clear"}}
            """
        let frame = try XCTUnwrap(InboundFrame.parse(text))
        XCTAssertEqual(frame.name, "ui_render")
        XCTAssertEqual(frame.renderComponents.count, 2)
        XCTAssertEqual(frame.renderComponents[0].textContent, "72 and clear")
        let speech = try XCTUnwrap(frame.speech)
        XCTAssertTrue(speech.ssml.hasPrefix("<speak>"))
        XCTAssertEqual(speech.text, "72 and clear")
    }

    func testUIRenderWithoutSpeechIsSilent() throws {
        let frame = try XCTUnwrap(
            InboundFrame.parse(
                #"{"type":"ui_render","components":[{"type":"text","content":"x"}]}"#))
        XCTAssertNil(frame.speech)  // absent field ⇒ silent delivery
    }

    func testUpsertOpsAndErrorNormalization() throws {
        let upsert = try XCTUnwrap(
            InboundFrame.parse(
                """
                {"type":"ui_upsert","chat_id":"c1","ops":[
                  {"op":"upsert","component_id":"wc_1","component":{"type":"alert","message":"done"}},
                  {"op":"remove","component_id":"wc_0"}]}
                """))
        XCTAssertEqual(upsert.chatId, "c1")
        XCTAssertEqual(upsert.upsertOps.count, 2)
        XCTAssertEqual(upsert.upsertOps[0].component?.message, "done")
        XCTAssertEqual(upsert.upsertOps[1].op, "remove")

        // 044 error normalization: message | payload.message | error
        for text in [
            #"{"type":"error","message":"boom"}"#,
            #"{"type":"error","payload":{"message":"boom"}}"#,
            #"{"type":"error","error":"boom"}"#,
        ] {
            XCTAssertEqual(InboundFrame.parse(text)?.errorMessage, "boom")
        }
    }

    func testComponentFallbackTextNeverBlank() {
        let mystery = AstralComponent(
            json: .object([
                "type": .string("hologram"), "title": .string("A 3D thing"),
            ]))!
        XCTAssertEqual(mystery.fallbackText, "A 3D thing")
        let bare = AstralComponent(json: .object(["type": .string("hologram")]))!
        XCTAssertEqual(bare.fallbackText, "[hologram]")
    }

    func testRegisterUICarriesDeviceAndResumed() throws {
        let text = Outbound.registerUI(
            token: "tok", sessionId: "s1",
            device: .watch(viewportWidth: 198, viewportHeight: 242),
            resumed: true)
        let json = try JSONValue.parse(Data(text.utf8))
        XCTAssertEqual(json["type"]?.stringValue, "register_ui")
        XCTAssertEqual(json["resumed"]?.boolValue, true)
        XCTAssertEqual(json["device"]?["device_type"]?.stringValue, "watch")
        XCTAssertEqual(json["device"]?["has_microphone"]?.boolValue, true)
        XCTAssertFalse(json["device"]?["supported_types"]?.arrayValue?.isEmpty ?? true)
    }

    func testChatMessageWithAttachments() throws {
        let text = Outbound.chatMessage(
            "read this", sessionId: "s1",
            attachments: [
                ChatAttachmentRef(
                    attachmentId: "a1", filename: "r.pdf",
                    category: "document")
            ])
        let json = try JSONValue.parse(Data(text.utf8))
        XCTAssertEqual(json["action"]?.stringValue, "chat_message")
        XCTAssertEqual(json["payload"]?["attachments"]?.arrayValue?.count, 1)
        XCTAssertEqual(
            json["payload"]?["attachments"]?.arrayValue?.first?["attachment_id"]?.stringValue,
            "a1")
    }
}
