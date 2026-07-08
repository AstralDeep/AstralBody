// Feature 051 US3 — the signed-out watch: backend-generated QR + short code
// + expiry countdown; no credential entry exists on the watch (FR-020).
import SwiftUI
import AstralCore

struct DeviceLoginView: View {
    @EnvironmentObject var model: WatchModel

    var body: some View {
        ScrollView {
            switch model.phase {
            case .waitingApproval, .signedOut:
                pending
            case .loginFailed(let reason):
                failure(title: "Not signed in", message: reason)
            case .unavailable(let detail):
                failure(title: "Sign-in unavailable", message: detail)
            case .signedIn:
                EmptyView()
            }
        }
        .navigationTitle("AstralDeep")
    }

    @ViewBuilder
    private var pending: some View {
        VStack(spacing: 6) {
            if let login = model.login {
                if let png = login.qrPNG, let image = UIImage(data: png) {
                    Image(uiImage: image)
                        .interpolation(.none)
                        .resizable()
                        .scaledToFit()
                        .accessibilityLabel("Sign-in QR code")
                } else {
                    ProgressView()
                }
                Text(login.userCode)
                    .font(.system(.title3, design: .monospaced).bold())
                    .accessibilityLabel("Sign-in code \(login.userCode)")
                Text("Scan with your phone camera, or enter the code at")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Text(login.verificationURI)
                    .font(.footnote.weight(.medium))
                    .multilineTextAlignment(.center)
                CountdownLine(until: model.loginExpiresAt)
            } else {
                ProgressView("Getting sign-in code…")
            }
        }
    }

    private func failure(title: String, message: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.circle")
                .font(.title2)
                .foregroundStyle(WatchBrand.warning)
            Text(title).font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Try again") { model.beginDeviceLogin() }
        }
    }
}

/// Advisory countdown only — expiry decisions are server-authoritative.
struct CountdownLine: View {
    let until: Date

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let remaining = max(0, Int(until.timeIntervalSince(context.date)))
            Text(remaining > 0 ? "Code refreshes in \(remaining)s" : "Refreshing…")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
    }
}
