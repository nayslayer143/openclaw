import UIKit

final class ThumbnailCache {
    static let shared = ThumbnailCache()
    private let cache = NSCache<NSString, UIImage>()
    private init() {
        cache.countLimit = 500
        cache.totalCostLimit = 100 * 1024 * 1024
    }
    func get(key: String) -> UIImage? {
        cache.object(forKey: key as NSString)
    }
    func set(key: String, image: UIImage) {
        let cost = Int(image.size.width * image.size.height * image.scale * 4)
        cache.setObject(image, forKey: key as NSString, cost: cost)
    }
}