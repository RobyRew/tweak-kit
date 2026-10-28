import UIKit

// App-agnostic window / view-controller lookup used by settings injection and UI
// features. Walks live scenes rather than the deprecated UIApplication.windows.
// Shared via tweak-kit.
enum WindowHelper {
    static var keyWindow: UIWindow? {
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
        return windows.first { $0.isKeyWindow } ?? windows.first
    }

    static var topViewController: UIViewController? {
        var vc = keyWindow?.rootViewController
        while let presented = vc?.presentedViewController { vc = presented }
        return vc
    }

    // Depth-first search of the live VC tree (children + presented) for the first
    // view controller whose class name equals or ends with `name`. The suffix
    // match tolerates module-prefixed Swift class names.
    static func firstViewController(ofClassNamed name: String) -> UIViewController? {
        guard let root = keyWindow?.rootViewController else { return nil }
        var stack = [root]
        while let vc = stack.popLast() {
            let cls = NSStringFromClass(type(of: vc))
            if cls == name || cls.hasSuffix(name) { return vc }
            stack.append(contentsOf: vc.children)
            if let presented = vc.presentedViewController { stack.append(presented) }
        }
        return nil
    }
}
