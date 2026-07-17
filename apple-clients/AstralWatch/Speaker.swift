// Feature 051 — on-device TTS for the server's spoken rendition (FR-030).
// Speaks `speech.ssml` via AVSpeechUtterance(ssmlRepresentation:), falling
// back to plain `text`. Never re-speaks a turn; navigation/stop obeys
// immediately; system silent/DND is honored by the platform audio session.
import AVFoundation
import AstralCore
import Observation

// The core package names the rendition `Speech`; alias locally so it can
// never collide with Apple's Speech framework module in app targets.
typealias AstralSpeech = AstralCore.Speech

@Observable
final class Speaker: NSObject {
    private let synthesizer = AVSpeechSynthesizer()
    @ObservationIgnored private var lastSpokenKey: Int?
    @ObservationIgnored private var lastSpeech: SpeechPayload?

    struct SpeechPayload {
        let ssml: String
        let text: String
    }

    var isSpeaking = false

    override init() {
        super.init()
        synthesizer.delegate = self
        #if os(watchOS)
            // Ambient: mixes politely and honors the system silent/DND state.
            try? AVAudioSession.sharedInstance().setCategory(.ambient, options: [.duckOthers])
        #endif
    }

    /// Speak a delivery's rendition exactly once. Dedup is keyed on the
    /// rendition CONTENT — frames carry no stable turn id, and a server
    /// re-push of the same canvas must never re-speak it (FR-030).
    func speak(_ speech: AstralSpeech?) {
        guard let speech else { return }
        let key = speech.text.hashValue
        guard key != lastSpokenKey else { return }
        lastSpokenKey = key
        let payload = SpeechPayload(ssml: speech.ssml, text: speech.text)
        lastSpeech = payload
        utter(payload)
    }

    func replay() {
        guard let last = lastSpeech else { return }
        stop()
        utter(last)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        isSpeaking = false
    }

    private func utter(_ payload: SpeechPayload) {
        let utterance: AVSpeechUtterance
        if !payload.ssml.isEmpty,
            let ssml = AVSpeechUtterance(ssmlRepresentation: payload.ssml)
        {
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
    func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didFinish utterance: AVSpeechUtterance
    ) {
        isSpeaking = false
    }

    func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didCancel utterance: AVSpeechUtterance
    ) {
        isSpeaking = false
    }
}
