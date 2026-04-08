import SwiftUI

/// Sheet that lets the user define a smart album by stacking rules.
/// Each rule has a Field, an Operator, and a Value. AND-combined.
struct CreateSmartAlbumSheet: View {
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var rules: [SmartRule] = [
        SmartRule(field: .favorite, op: .isTrue, value: "true")
    ]

    private var canSave: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && !rules.isEmpty
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                ScrollView {
                    VStack(spacing: 18) {
                        nameSection
                        rulesSection
                        Button {
                            withAnimation(Theme.Motion.snappy) {
                                rules.append(SmartRule(
                                    field: .rating,
                                    op: .atLeast,
                                    value: "3"
                                ))
                            }
                        } label: {
                            HStack {
                                Image(systemName: "plus.circle.fill")
                                Text("Add Rule")
                            }
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(Theme.Palette.accent)
                        }
                        .buttonStyle(.plain)
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
            Text("New Smart Album")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Button("Cancel") {
                    Haptics.tap()
                    dismiss()
                }
                .font(.system(size: 17))
                .foregroundStyle(Theme.Palette.accent)
                Spacer()
                Button("Save") {
                    Haptics.success()
                    dataManager.createSmartAlbum(name: name, rules: rules)
                    dismiss()
                }
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(canSave ? Theme.Palette.accent : Theme.Palette.textDim)
                .disabled(!canSave)
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

    private var nameSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("NAME")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)
            TextField("e.g. Best of 2026", text: $name)
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

    private var rulesSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("RULES (ALL MUST MATCH)")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)

            VStack(spacing: 8) {
                ForEach(rules.indices, id: \.self) { i in
                    ruleEditor(index: i)
                }
            }
        }
    }

    @ViewBuilder
    private func ruleEditor(index: Int) -> some View {
        let rule = rules[index]
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                // Field
                Picker("Field", selection: Binding(
                    get: { rules[index].field },
                    set: {
                        rules[index].field = $0
                        // Reset operator to a sensible default for the field.
                        switch $0 {
                        case .favorite, .hidden:
                            rules[index].op = .isTrue
                            rules[index].value = "true"
                        case .rating:
                            rules[index].op = .atLeast
                            rules[index].value = "3"
                        case .eventBucket:
                            rules[index].op = .contains
                            rules[index].value = "March"
                        }
                    }
                )) {
                    ForEach(SmartRule.Field.allCases) { f in
                        Text(f.label).tag(f)
                    }
                }
                .pickerStyle(.menu)
                .tint(Theme.Palette.accent)

                Spacer()

                Button {
                    Haptics.tap()
                    withAnimation { rules.remove(at: index) }
                } label: {
                    Image(systemName: "minus.circle.fill")
                        .font(.system(size: 19))
                        .foregroundStyle(.red.opacity(0.85))
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 8) {
                Picker("Op", selection: Binding(
                    get: { rules[index].op },
                    set: { rules[index].op = $0 }
                )) {
                    ForEach(operators(for: rule.field), id: \.self) { op in
                        Text(op.label).tag(op)
                    }
                }
                .pickerStyle(.menu)
                .tint(Theme.Palette.accent)

                if needsValueField(rule) {
                    TextField("Value", text: Binding(
                        get: { rules[index].value },
                        set: { rules[index].value = $0 }
                    ))
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 140)
                }
                Spacer()
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.Palette.bgElevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
        .padding(.horizontal, 16)
    }

    private func operators(for field: SmartRule.Field) -> [SmartRule.Op] {
        switch field {
        case .favorite, .hidden: return [.isTrue, .isFalse]
        case .rating:            return [.atLeast, .equals]
        case .eventBucket:       return [.contains]
        }
    }

    private func needsValueField(_ rule: SmartRule) -> Bool {
        switch rule.field {
        case .favorite, .hidden: return false
        case .rating, .eventBucket: return true
        }
    }
}
