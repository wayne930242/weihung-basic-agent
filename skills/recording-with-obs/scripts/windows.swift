// Lists on-screen windows of one app, front to back: "<CGWindowID>\t<width>x<height>\t<title>".
// Windows under 200x150 points (Chrome's infobars and popups) are skipped.
// OBS's macOS Screen Capture source takes this CGWindowID as its "window" setting.
import CoreGraphics

let owner = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Google Chrome"
let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
for window in list {
  guard (window[kCGWindowOwnerName as String] as? String) == owner,
        (window[kCGWindowLayer as String] as? Int) == 0,
        let id = window[kCGWindowNumber as String] as? Int,
        let bounds = window[kCGWindowBounds as String] as? [String: Any] else { continue }
  let width = bounds["Width"] as? Int ?? 0
  let height = bounds["Height"] as? Int ?? 0
  guard width >= 200, height >= 150 else { continue }
  let title = window[kCGWindowName as String] as? String ?? ""
  print("\(id)\t\(width)x\(height)\t\(title)")
}
