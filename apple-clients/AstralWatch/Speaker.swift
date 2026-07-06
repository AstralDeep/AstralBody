// Feature 051 — on-device TTS for the server's spoken rendition (FR-030).
// Speaks `speech.ssml` via AVSpeechUtterance(ssmlRepresentation:), falling
// back to plain `text`. Never re-speaks a turn; navigation/stop obeys
// immediately; system silent/DND is honored by the platform audio session.
import AVFoundation
import AstralCore

// The core package names the rendition `Speech`; alias locally so it can
// never collide with Apple's Speech framework module in app targets.
typealias AstralSpeech = AstralCore.Speech

final class Speaker: NSObject, ObservableObject {
    private let synthesizer = AVSpeechSynthesizer()
    private var lastSpokenTurnId: String?
    private var lastSpeech: (speech: SpeechPayload, turnId: String)?

    struct SpeechPayload {
        let ssml: String
        let text: String
    }

    @Published var isSpeaking = false

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    /// Speak a delivery's rendition exactly once (`turnId` de-dupes; the
    /// server never re-sends speech for re-adapted content, and we never
    /// re-speak a turn we already voiced — FR-030).
    func speak(_ speech: AstralSpeech?, turnId: String) {
        guard let speech, turnId != lastSpokenTurnId else { return }
        lastSpokenTurnId = turnId
        let payload = SpeechPayload(ssml: speech.ssml, text: speech.text)
        lastSpeech = (payload, turnId)
        utter(payload)
    }

    func replay() {
        guard let last = lastSpeech else { return }
        stop()
        utter(last.speech)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        isSpeaking = false
    }

    private func utter(_ payload: SpeechPayload) {
        let utterance: AVSpeechUtterance
        if !payload.ssml.isEmpty,
           let ssml = AVSpeechUtterance(ssmlRepresentation: payload.ssml) {
            utterance = ssml
        } else if !payload.text.isEmpty {
            utterance = AVSpeechUtterance(string: payload.text)
        } else {
            return
        }
        isSpeaking = true
        synthesizer.speak(utterance)
    }
}

extension Speaker: AVSpeechSynthesizerDelegate {
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                           didFinish utterance: AVSpeechUtterance) {
        isSpeaking = false
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer,
                           didCancel utterance: AVSpeechUtterance) {
        isSpeaking = false
    }
}
