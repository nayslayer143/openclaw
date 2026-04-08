import SwiftUI
import Combine

/// Auto-advancing fullscreen slideshow with cross-fade transitions.
/// Tap to toggle play/pause + show controls. Swipe down to dismiss.
struct SlideshowView: View {
    let photoIds: [String]
    var interval: TimeInterval = 3.5

    @EnvironmentObject var photoKitService: PhotoKitService
    @Environment(\.dismiss) private var dismiss

    @State private var currentIndex: Int = 0
    @State private var isPlaying: Bool = true
    @State private var chromeVisible: Bool = false
    @State private var timer: AnyCancellable?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            // Crossfade between sequential photos.
            ForEach(Array(photoIds.enumerated()), id: \.offset) { index, identifier in
                if index == currentIndex {
                    SlideshowFrame(identifier: identifier)
                        .transition(.opacity.animation(.easeInOut(duration: 0.6)))
                }
            }

            if chromeVisible {
                topBar.frame(maxHeight: .infinity, alignment: .top)
                bottomBar.frame(maxHeight: .infinity, alignment: .bottom)
            }
        }
        .ignoresSafeArea()
        .onTapGesture {
            withAnimation(Theme.Motion.snappy) {
                chromeVisible.toggle()
            }
        }
        .onAppear { startTimer() }
        .onDisappear { stopTimer() }
        .gesture(
            DragGesture(minimumDistance: 30)
                .onEnded { value in
                    if value.translation.height > 80 {
                        Haptics.tap()
                        dismiss()
                    }
                }
        )
    }

    // MARK: - Chrome

    private var topBar: some View {
        HStack {
            Button { Haptics.tap(); dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(Color.black.opacity(0.45)))
            }
            .buttonStyle(.plain)
            Spacer()
            Text("\(currentIndex + 1) of \(photoIds.count)")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Capsule().fill(Color.black.opacity(0.45)))
            Spacer()
            Color.clear.frame(width: 38, height: 38)
        }
        .padding(.horizontal, 14)
        .padding(.top, 56)
    }

    private var bottomBar: some View {
        HStack(spacing: 24) {
            playButton(systemName: "backward.fill") {
                advance(by: -1)
            }
            playButton(systemName: isPlaying ? "pause.fill" : "play.fill") {
                togglePlay()
            }
            playButton(systemName: "forward.fill") {
                advance(by: 1)
            }
        }
        .padding(.bottom, 36)
    }

    private func playButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 50, height: 50)
                .background(Circle().fill(Color.black.opacity(0.45)))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Timer

    private func startTimer() {
        guard isPlaying else { return }
        stopTimer()
        timer = Timer.publish(every: interval, on: .main, in: .common)
            .autoconnect()
            .sink { _ in advance(by: 1) }
    }

    private func stopTimer() {
        timer?.cancel()
        timer = nil
    }

    private func togglePlay() {
        isPlaying.toggle()
        if isPlaying {
            startTimer()
        } else {
            stopTimer()
        }
    }

    private func advance(by delta: Int) {
        guard !photoIds.isEmpty else { return }
        let next = (currentIndex + delta + photoIds.count) % photoIds.count
        withAnimation { currentIndex = next }
    }
}

private struct SlideshowFrame: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    private var isDemo: Bool { identifier.hasPrefix("demo:") }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if isDemo {
                    LinearGradient(
                        colors: [
                            DemoPalette.color(for: identifier),
                            DemoPalette.color(for: identifier).opacity(0.55)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    Image(systemName: DemoPalette.icon(for: identifier))
                        .font(.system(size: 120, weight: .light))
                        .foregroundStyle(.white.opacity(0.85))
                } else if let img = image {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFit()
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            // Subtle Ken Burns zoom — slow scale that resets per frame.
            .scaleEffect(1.0)
            .animation(.easeInOut(duration: 6.0), value: identifier)
        }
        .task(id: identifier) {
            guard !isDemo else { return }
            image = await photoKitService.loadFullImage(for: identifier)
        }
    }
}
