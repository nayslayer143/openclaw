import SwiftUI
import MapKit
import Photos

/// MapKit-backed view of geotagged photos. Each photo with a location
/// becomes a pin; pins are clustered automatically by MKMapView at lower
/// zoom levels. Tapping a pin shows a small popover with the cover and a
/// chevron to open that photo.
struct PlacesView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var pins: [PlacePin] = []
    @State private var isLoading = true
    @State private var cameraPosition: MapCameraPosition = .automatic

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                BrandTopBar(
                    title: "Places",
                    subtitle: pins.isEmpty
                        ? (isLoading ? "Scanning library…" : "No geotagged photos")
                        : "\(pins.count) location\(pins.count == 1 ? "" : "s")",
                    onBack: { dismiss() },
                    onHome: { navCoordinator.popToRoot() }
                )

                if isLoading {
                    loading
                } else if pins.isEmpty {
                    empty
                } else {
                    Map(position: $cameraPosition) {
                        ForEach(pins) { pin in
                            Annotation(
                                pin.label,
                                coordinate: pin.coordinate
                            ) {
                                PlacePinMarker(pin: pin) {
                                    Haptics.tap()
                                    navCoordinator.path.append(
                                        PhotoViewerRoute(
                                            photoIds: pin.photoIds,
                                            startIndex: 0
                                        )
                                    )
                                }
                            }
                        }
                    }
                    .mapStyle(.standard(elevation: .realistic))
                    .ignoresSafeArea(edges: .bottom)
                }
            }
        }
        .navigationBarHidden(true)
        .task { await load() }
    }

    private var loading: some View {
        VStack {
            Spacer()
            ProgressView().tint(Theme.Palette.accent)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "mappin.slash")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No Geotagged Photos")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Photos with location data will appear here on a map.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    @MainActor
    private func load() async {
        defer { isLoading = false }
        let raw: [String]
        if DemoLibrary.isEnabled {
            raw = DemoLibrary.identifiers
        } else {
            raw = photoKitService.fetchAllAssetIdentifiers()
        }
        let excluded = dataManager.excludedAssetIdSet()
        let visible = raw.filter { !excluded.contains($0) }

        // Group by rounded coordinate so multiple photos taken in the
        // same spot collapse to one pin.
        var grouped: [String: PlacePin] = [:]
        for id in visible {
            guard let info = await PhotoMetadataLoader.load(identifier: id),
                  info.hasLocation,
                  let coords = parseCoordinates(info.coordinates ?? "") else { continue }
            // Bucket by ~0.05° so nearby shots cluster.
            let key = String(format: "%.2f,%.2f", coords.latitude, coords.longitude)
            if var existing = grouped[key] {
                existing.photoIds.append(id)
                grouped[key] = existing
            } else {
                let label = info.coordinates?.split(separator: "·").last
                    .map { $0.trimmingCharacters(in: .whitespaces) } ?? "Location"
                grouped[key] = PlacePin(
                    id: key,
                    coordinate: coords,
                    label: label,
                    photoIds: [id]
                )
            }
        }

        pins = Array(grouped.values).sorted { $0.photoIds.count > $1.photoIds.count }

        if let first = pins.first {
            cameraPosition = .region(
                MKCoordinateRegion(
                    center: first.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 60, longitudeDelta: 60)
                )
            )
        }
    }

    private func parseCoordinates(_ str: String) -> CLLocationCoordinate2D? {
        // Format: "37.77490, -122.41940  · San Francisco"
        let head = str.split(separator: "·").first.map { String($0) } ?? str
        let parts = head.split(separator: ",").map {
            $0.trimmingCharacters(in: .whitespaces)
        }
        guard parts.count == 2,
              let lat = Double(parts[0]),
              let lon = Double(parts[1]) else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

struct PlacePin: Identifiable {
    let id: String
    let coordinate: CLLocationCoordinate2D
    let label: String
    var photoIds: [String]
}

private struct PlacePinMarker: View {
    let pin: PlacePin
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 2) {
                ZStack {
                    Circle()
                        .fill(Theme.Palette.accent)
                        .frame(width: 36, height: 36)
                    Circle()
                        .strokeBorder(Color.white, lineWidth: 2)
                        .frame(width: 36, height: 36)
                    Text("\(pin.photoIds.count)")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(.white)
                }
                .shadow(color: .black.opacity(0.3), radius: 4, x: 0, y: 2)
                Text(pin.label)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(Color.black.opacity(0.65)))
            }
        }
        .buttonStyle(.plain)
    }
}
