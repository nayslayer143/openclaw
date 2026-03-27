import SwiftUI

struct ImportProgressView: View {
    @ObservedObject var importService: LibraryImportService
    let onDismiss: () -> Void

    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                Spacer()
                icon
                statusText
                if importService.isImporting {
                    counters
                    progressBar
                } else if !importService.authorizationDenied {
                    counters
                    doneButton
                } else {
                    settingsButton
                }
                Spacer()
            }
            .padding(.horizontal, 32)
            .navigationTitle("Import Library")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !importService.isImporting {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done", action: onDismiss)
                            .fontWeight(.semibold)
                    }
                }
            }
            .interactiveDismissDisabled(importService.isImporting)
        }
    }

    // MARK: Sub-views

    @ViewBuilder
    private var icon: some View {
        if importService.isImporting {
            ProgressView()
                .scaleEffect(1.8)
                .padding(.bottom, 8)
        } else if importService.authorizationDenied {
            Image(systemName: "lock.shield")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(.orange)
        } else if importService.progress >= 1.0 {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(.green)
        } else {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(.secondary)
        }
    }

    private var statusText: some View {
        Text(importService.statusMessage)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .animation(.easeInOut, value: importService.statusMessage)
    }

    private var counters: some View {
        HStack(spacing: 32) {
            VStack(spacing: 4) {
                Text("\(importService.importedFolderCount)")
                    .font(.title2.monospacedDigit().weight(.semibold))
                Label("Folders", systemImage: "folder.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            VStack(spacing: 4) {
                Text("\(importService.importedPhotoCount)")
                    .font(.title2.monospacedDigit().weight(.semibold))
                Label("Photos", systemImage: "photo")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 8)
    }

    private var progressBar: some View {
        VStack(spacing: 8) {
            ProgressView(value: importService.progress)
                .progressViewStyle(.linear)
                .tint(.blue)
            Text("\(Int(importService.progress * 100))%")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.tertiary)
        }
    }

    private var doneButton: some View {
        Button("Done", action: onDismiss)
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
    }

    private var settingsButton: some View {
        Button {
            if let url = URL(string: UIApplication.openSettingsURLString) {
                UIApplication.shared.open(url)
            }
        } label: {
            Label("Open Settings", systemImage: "gear")
        }
        .buttonStyle(.bordered)
        .controlSize(.large)
    }
}
