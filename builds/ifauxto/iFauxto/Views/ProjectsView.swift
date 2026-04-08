import SwiftUI

/// Lists existing creative projects (collages, books, cards, calendars)
/// and lets the user create new ones. Tapping a project opens its
/// dedicated detail view.
struct ProjectsView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var projects: [PhotoProject] = []
    @State private var showingTypePicker = false

    private let columns = [
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14)
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                BrandTopBar(
                    title: "Projects",
                    subtitle: projects.isEmpty ? nil : "\(projects.count) project\(projects.count == 1 ? "" : "s")",
                    onBack: { dismiss() },
                    onHome: { navCoordinator.popToRoot() }
                ) {
                    Button {
                        Haptics.tap()
                        showingTypePicker = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                    .buttonStyle(.plain)
                }

                if projects.isEmpty {
                    empty
                } else {
                    grid
                }
            }
        }
        .navigationBarHidden(true)
        .sheet(isPresented: $showingTypePicker, onDismiss: reload) {
            ProjectTypePickerSheet { type, name in
                dataManager.createProject(name: name, type: type)
                Haptics.success()
            }
        }
        .onAppear { reload() }
    }

    private var grid: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(projects) { project in
                    NavigationLink {
                        CollageEditorView(project: project)
                    } label: {
                        ProjectCard(project: project)
                    }
                    .buttonStyle(PressableButtonStyle(scale: 0.97))
                    .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 40)
        }
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "square.grid.3x3.square")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No Projects Yet")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Create a collage, photo book, card, or calendar to get started.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Button {
                Haptics.tap()
                showingTypePicker = true
            } label: {
                Text("New Project")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Theme.Palette.accent)
                    )
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func reload() {
        projects = dataManager.fetchProjects()
    }
}

private struct ProjectCard: View {
    let project: PhotoProject

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack {
                LinearGradient(
                    colors: [
                        Theme.Palette.accent.opacity(0.18),
                        Theme.Palette.accent.opacity(0.05)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Image(systemName: project.type.icon)
                    .font(.system(size: 38, weight: .light))
                    .foregroundStyle(Theme.Palette.accent)
            }
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )

            VStack(alignment: .leading, spacing: 1) {
                Text(project.name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                Text(project.type.label)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
            }
        }
    }
}

/// Sheet that asks the user to pick a project type and give it a name.
struct ProjectTypePickerSheet: View {
    let onCreate: (ProjectType, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name: String = ""
    @State private var type: ProjectType = .collage

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                ScrollView {
                    VStack(spacing: 18) {
                        nameField
                        typeGrid
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 40)
                }
            }
        }
    }

    private var topBar: some View {
        ZStack {
            Text("New Project")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Button("Cancel") { Haptics.tap(); dismiss() }
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.accent)
                Spacer()
                Button("Create") {
                    let trimmed = name.trimmingCharacters(in: .whitespaces)
                    onCreate(type, trimmed.isEmpty ? "Untitled \(type.label)" : trimmed)
                    dismiss()
                }
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.accent)
            }
            .padding(.horizontal, 16)
            .buttonStyle(.plain)
        }
        .frame(height: 44)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(Theme.Palette.bg)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    private var nameField: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("NAME")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)
            TextField("e.g. Summer Collage", text: $name)
                .font(.system(size: 17))
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Theme.Palette.bgElevated)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                )
        }
    }

    private var typeGrid: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("TYPE")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)

            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12)
            ], spacing: 12) {
                ForEach(ProjectType.allCases) { t in
                    Button {
                        Haptics.select()
                        type = t
                    } label: {
                        VStack(spacing: 8) {
                            Image(systemName: t.icon)
                                .font(.system(size: 30, weight: .light))
                                .foregroundStyle(type == t ? Theme.Palette.accent : Theme.Palette.text)
                                .frame(height: 44)
                            Text(t.label)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(type == t ? Theme.Palette.accent : Theme.Palette.text)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 18)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Theme.Palette.bgElevated)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .strokeBorder(
                                    type == t ? Theme.Palette.accent : Theme.Palette.stroke,
                                    lineWidth: type == t ? 2 : 0.5
                                )
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }
}
