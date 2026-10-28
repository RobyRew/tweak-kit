import Foundation

// Codable-backed UserDefaults property wrapper. Stores the JSON encoding of any
// Codable value under `key` (optionally in a named suite). App-agnostic; shared
// across tweaks via tweak-kit.
//
//   extension UserDefaults {
//       @UserDefault(key: "lproFeedFilter", defaultValue: FeedFilterOptions())
//       static var feedFilterOptions
//   }
@propertyWrapper
struct UserDefault<Value: Codable> {
    let key: String
    let defaultValue: Value
    let store: UserDefaults

    init(key: String, defaultValue: Value, suite: String? = nil) {
        self.key = key
        self.defaultValue = defaultValue
        self.store = suite.flatMap(UserDefaults.init(suiteName:)) ?? .standard
    }

    var wrappedValue: Value {
        get {
            guard let data = store.data(forKey: key),
                  let decoded = try? JSONDecoder().decode(Value.self, from: data) else {
                return defaultValue
            }
            return decoded
        }
        set {
            if let data = try? JSONEncoder().encode(newValue) {
                store.set(data, forKey: key)
            }
        }
    }
}
