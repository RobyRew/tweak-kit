import Foundation

// App-agnostic file + console logger. Writes to NSTemporaryDirectory()/<filename>
// (pullable over USB with striker / devicectl) and mirrors to NSLog with a tag.
// Shared via tweak-kit.
final class TweakLog {
    private let tag: String
    private let path: String

    init(tag: String, filename: String) {
        self.tag = tag
        self.path = (NSTemporaryDirectory() as NSString).appendingPathComponent(filename)
    }

    func write(_ message: String) {
        NSLog("[%@] %@", tag, message)
        let line = "[\(Date())] \(message)\n"
        guard let data = line.data(using: .utf8) else { return }
        if FileManager.default.fileExists(atPath: path), let fh = FileHandle(forWritingAtPath: path) {
            fh.seekToEndOfFile()
            fh.write(data)
            fh.closeFile()
        } else {
            try? line.write(toFile: path, atomically: true, encoding: .utf8)
        }
    }
}
