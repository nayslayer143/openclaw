import SwiftUI
import Photos
import CoreLocation

struct PhotoViewer: View {
    let photoIds: [String]
    let startIndex: Int

    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var navCoordinator: NavCoordinator
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss
    @State private var currentIndex: Int
    @State private var showingEditor = false
    @State private var showingInfo = false
    @State private var chromeVisible = true
    @State private var isFavorite = false

    init(photoIds: [String], startIndex: Int) {
        self.photoIds = photoIds
        self.startIndex = startIndex
        _currentIndex = State(initialValue: startIndex)
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-autoShowInfo") {
            _showingInfo = State(initialValue: true)
        }
        #endif
    }

    private var currentId: String {
        guard photoIds.indices.contains(currentIndex) else { return photoIds.first ?? "" }
        return photoIds[currentIndex]
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            TabView(selection: $currentIndex) {
                ForEach(Array(photoIds.enumerated()), id: \.offset) { index, identifier in
                    FullPhotoView(identifier: identifier)
                        .tag(index)
                        .onTapGesture {
                            withAnimation(Theme.Motion.snappy) {
                                chromeVisible.toggle()
                            }
                        }
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            if chromeVisible {
                topBar
                    .frame(maxHeight: .infinity, alignment: .top)
                    .transition(.move(edge: .top).combined(with: .opacity))

                bottomBar
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .ignoresSafeArea()
        .toolbar(.hidden, for: .navigationBar)
        .statusBarHidden(!chromeVisible)
        .sheet(isPresented: $showingEditor) {
            PhotoEditorView(photoIdentifier: currentId)
        }
        .sheet(isPresented: $showingInfo) {
            PhotoInfoSheet(identifier: currentId)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .onAppear {
            currentIndex = startIndex
            refreshFavorite()
        }
        .onChange(of: currentIndex) { _, _ in
            refreshFavorite()
        }
    }

    private func refreshFavorite() {
        isFavorite = dataManager.metaIfExists(for: currentId)?.isFavorite ?? false
    }

    private func toggleFavorite() {
        isFavorite = dataManager.toggleFavorite(for: currentId)
        Haptics.success()
    }

    // MARK: - Chrome

    private var topBar: some View {
        HStack(spacing: 8) {
            PhotoOverlayButton(systemName: "chevron.left") { dismiss() }
            PhotoOverlayButton(systemName: "house.fill") { navCoordinator.popToRoot() }
            Spacer()
            Text("\(currentIndex + 1) of \(photoIds.count)")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Capsule().fill(Color.black.opacity(0.45)))
            Spacer()
            PhotoOverlayButton(systemName: "info.circle") { showingInfo = true }
            PhotoOverlayButton(systemName: "slider.horizontal.3") { showingEditor = true }
        }
        .padding(.horizontal, 14)
        .padding(.top, 56)
    }

    private var bottomBar: some View {
        HStack(spacing: 14) {
            Spacer()
            PhotoOverlayButton(systemName: "square.and.arrow.up") { /* share, future */ }
            PhotoOverlayButton(
                systemName: isFavorite ? "heart.fill" : "heart",
                tint: isFavorite ? Color(red: 1.0, green: 0.30, blue: 0.30) : .white
            ) { toggleFavorite() }
            PhotoOverlayButton(systemName: "trash") { trashCurrent() }
            Spacer()
        }
        .padding(.bottom, 36)
    }

    private func trashCurrent() {
        Haptics.warning()
        dataManager.moveToTrash(currentId)
        // Pop back so we don't strand the user on a deleted photo.
        dismiss()
    }
}

// MARK: - Full photo view (zoomable)

private struct FullPhotoView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    @State private var scale: CGFloat = 1
    @State private var lastScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    private var isDemo: Bool { identifier.hasPrefix("demo:") }

    var body: some View {
        GeometryReader { geo in
            Group {
                if isDemo {
                    demoArt
                        .frame(width: geo.size.width, height: geo.size.height)
                } else if let img = image {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFit()
                        .frame(width: geo.size.width, height: geo.size.height)
                } else {
                    ProgressView()
                        .tint(.white)
                        .frame(width: geo.size.width, height: geo.size.height)
                }
            }
            .scaleEffect(scale)
            .offset(offset)
            .gesture(zoomGesture(viewport: geo.size))
            .simultaneousGesture(panGesture(viewport: geo.size))
            .onTapGesture(count: 2) {
                Haptics.medium()
                withAnimation(.spring(response: 0.35, dampingFraction: 0.78)) {
                    if scale > 1.01 {
                        scale = 1
                        lastScale = 1
                        offset = .zero
                        lastOffset = .zero
                    } else {
                        scale = 2.5
                        lastScale = 2.5
                    }
                }
            }
        }
        .task(id: identifier) {
            guard !isDemo else { return }
            image = await photoKitService.loadFullImage(for: identifier)
        }
        .onChange(of: identifier) { _, _ in
            // Reset zoom when swiping to a new photo.
            scale = 1; lastScale = 1
            offset = .zero; lastOffset = .zero
        }
    }

    private var demoArt: some View {
        ZStack {
            LinearGradient(
                colors: [
                    DemoPalette.color(for: identifier),
                    DemoPalette.color(for: identifier).opacity(0.55)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            VStack(spacing: 24) {
                Image(systemName: DemoPalette.icon(for: identifier))
                    .font(.system(size: 96, weight: .light))
                    .foregroundStyle(.white.opacity(0.85))
                Text(DemoPalette.label(for: identifier))
                    .font(.system(size: 28, weight: .semibold).monospacedDigit())
                    .foregroundStyle(.white.opacity(0.95))
                    .padding(.horizontal, 18)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(.black.opacity(0.30)))
            }
        }
    }

    private func zoomGesture(viewport: CGSize) -> some Gesture {
        MagnificationGesture()
            .onChanged { value in
                let next = lastScale * value
                scale = max(1, min(next, 5))
            }
            .onEnded { _ in
                lastScale = scale
                if scale < 1.05 {
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.82)) {
                        scale = 1
                        lastScale = 1
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    private func panGesture(viewport: CGSize) -> some Gesture {
        DragGesture()
            .onChanged { value in
                guard scale > 1.01 else { return }
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
            }
            .onEnded { _ in
                lastOffset = offset
            }
    }
}

// MARK: - Overlay button

/// Dark-capsule icon button for chrome floating over a photo background.
private struct PhotoOverlayButton: View {
    let systemName: String
    var tint: Color = .white
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 38, height: 38)
                .background(Circle().fill(Color.black.opacity(0.45)))
        }
        .buttonStyle(.plain)
    }
}
