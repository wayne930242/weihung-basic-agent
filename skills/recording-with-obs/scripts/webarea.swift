// Prints how far Chrome's web content sits inside one window, in points:
// "<top> <left> <bottom> <right> <windowWidth> <windowHeight>".
// Usage: swift webarea.swift <CGWindowID>. Needs the Accessibility permission.
import ApplicationServices
import CoreGraphics

@_silgen_name("_AXUIElementGetWindow")
func axWindowID(_ element: AXUIElement, _ id: UnsafeMutablePointer<CGWindowID>) -> AXError

func attribute<T>(_ element: AXUIElement, _ name: String) -> T? {
  var value: CFTypeRef?
  guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
  return value as? T
}

func frame(_ element: AXUIElement) -> CGRect? {
  guard let pos: AXValue = attribute(element, kAXPositionAttribute),
        let size: AXValue = attribute(element, kAXSizeAttribute) else { return nil }
  var origin = CGPoint.zero, extent = CGSize.zero
  AXValueGetValue(pos, .cgPoint, &origin)
  AXValueGetValue(size, .cgSize, &extent)
  return CGRect(origin: origin, size: extent)
}

func fail(_ message: String) -> Never {
  FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
  exit(1)
}

guard CommandLine.arguments.count > 1, let target = CGWindowID(CommandLine.arguments[1]) else { fail("usage: webarea.swift <CGWindowID>") }
guard AXIsProcessTrusted() else { fail("this terminal lacks the Accessibility permission") }

let info = CGWindowListCopyWindowInfo([.optionIncludingWindow], target) as? [[String: Any]] ?? []
guard let pid = info.first?[kCGWindowOwnerPID as String] as? pid_t else { fail("no window \(target)") }

let app = AXUIElementCreateApplication(pid)
let windows: [AXUIElement] = attribute(app, kAXWindowsAttribute) ?? []
guard let window = windows.first(where: { var id: CGWindowID = 0; return axWindowID($0, &id) == .success && id == target }),
      let windowFrame = frame(window) else { fail("window \(target) not found through Accessibility") }

// Breadth-first search for the largest web area, without descending into page content.
func largestWebArea() -> CGRect? {
  var queue = [window], best: CGRect?
  while !queue.isEmpty {
    let element = queue.removeFirst()
    if (attribute(element, kAXRoleAttribute) as String?) == "AXWebArea" {
      if let f = frame(element), f.width * f.height > (best.map { $0.width * $0.height } ?? 0) { best = f }
      continue
    }
    queue += (attribute(element, kAXChildrenAttribute) as [AXUIElement]?) ?? []
  }
  return best
}

// Chrome exposes web content only after an assistive client asks for it, so the first
// search can come back empty. AXEnhancedUserInterface is reset afterwards because window
// managers such as AeroSpace move windows slowly while it is on.
var web = largestWebArea()
if web == nil {
  AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
  for _ in 0..<60 where web == nil {
    usleep(250_000)
    web = largestWebArea()
  }
  AXUIElementSetAttributeValue(app, "AXEnhancedUserInterface" as CFString, kCFBooleanFalse)
}
guard let web else { fail("no web content found in window \(target); is a page loaded?") }

let top = web.minY - windowFrame.minY, left = web.minX - windowFrame.minX
let bottom = windowFrame.maxY - web.maxY, right = windowFrame.maxX - web.maxX
print(Int(top), Int(left), Int(bottom), Int(right), Int(windowFrame.width), Int(windowFrame.height))
