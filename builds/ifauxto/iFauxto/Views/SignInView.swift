import SwiftUI
import AuthenticationServices

/// First-launch / unauthenticated entry view. Offers Sign in with Apple
/// (real flow) plus a "continue without account" option that drops the
/// user into the guest bucket.
struct SignInView: View {
    @EnvironmentObject var dataManager: DataManager
    @ObservedObject var session = UserSession.shared

    let onAuthenticated: () -> Void

    var body: some View {
        ZStack {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                Image(systemName: "photo.stack.fill")
                    .font(.system(size: 64, weight: .regular))
                    .foregroundStyle(Theme.Palette.folder)
                    .symbolRenderingMode(.hierarchical)

                VStack(spacing: 8) {
                    Text("iFauxto")
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(Theme.Palette.text)
                    Text("Your photos. Your order.")
                        .font(.system(size: 16))
                        .foregroundStyle(Theme.Palette.textMuted)
                }

                Spacer()

                VStack(spacing: 12) {
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handle(result: result)
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 50)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal, 20)

                    Button {
                        Haptics.tap()
                        session.continueAsGuest()
                        onAuthenticated()
                    } label: {
                        Text("Continue without an account")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.bottom, 36)

                Text("Your photos stay on this device.\nSign in to back up to iCloud and sync across devices.")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .padding(.bottom, 24)
            }
        }
    }

    private func handle(result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let auth):
            guard let credential = auth.credential as? ASAuthorizationAppleIDCredential else { return }
            session.signInWithApple(credential: credential, dataManager: dataManager)
            Haptics.success()
            onAuthenticated()
        case .failure:
            Haptics.error()
        }
    }
}
