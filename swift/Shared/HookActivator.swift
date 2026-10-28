import Foundation
import ObjectiveC.runtime
import Orion

// App-agnostic, version-independent hook activation. A feature's Orion HookGroup
// is activated only after its target classes (and optional selectors) are
// confirmed present in the RUNNING host build, by runtime name. This is what
// keeps a tweak from being pinned to one host version: a renamed/removed class
// becomes a logged skip, not a crash. Shared via tweak-kit.
enum HookActivator {
    @discardableResult
    static func activate(_ group: HookGroup, named name: String,
                         requiring classes: [String],
                         selectors: [(className: String, selector: Selector)] = [],
                         log: (String) -> Void) -> Bool {
        let missing = classes.filter { NSClassFromString($0) == nil }
        guard missing.isEmpty else {
            log("skip \(name): missing classes \(missing)")
            return false
        }
        for pair in selectors {
            guard let cls = NSClassFromString(pair.className),
                  class_getInstanceMethod(cls, pair.selector) != nil
                    || class_getClassMethod(cls, pair.selector) != nil else {
                log("skip \(name): \(pair.className) lacks \(pair.selector)")
                return false
            }
        }
        group.activate()
        log("activated \(name)")
        return true
    }

    // Resolves a class by a demangled-name suffix, for lazily-registered Swift
    // classes whose exact (mangled) name is unknown or unstable across versions.
    static func firstClass(suffix: String) -> AnyClass? {
        var count: UInt32 = 0
        guard let list = objc_copyClassList(&count) else { return nil }
        defer { free(UnsafeMutableRawPointer(list)) }
        for i in 0..<Int(count) where String(cString: class_getName(list[i])).hasSuffix(suffix) {
            return list[i]
        }
        return nil
    }
}
