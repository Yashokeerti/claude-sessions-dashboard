import Cocoa
import WebKit

// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var statusItem: NSStatusItem!
    var serverProcess: Process?
    var serverReady = false
    let port = 8050
    let pythonScript: String = {
        // Look for the dashboard script in known locations
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let candidates = [
            "\(home)/claude-sessions-dashboard.py",
            Bundle.main.resourcePath.map { "\($0)/claude-sessions-dashboard.py" } ?? ""
        ]
        for path in candidates {
            if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }
        return "\(home)/claude-sessions-dashboard.py"
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenuBar()
        startServer()
        waitForServerAndOpenWindow()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopServer()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            window?.makeKeyAndOrderFront(nil)
        }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ application: NSApplication) -> Bool {
        return false  // Keep running in menu bar
    }

    // MARK: - Menu Bar

    func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem.button {
            button.title = "CS"
            button.toolTip = "Claude Sessions Dashboard"
        }

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Refresh", action: #selector(refreshDashboard), keyEquivalent: "r"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Restart Server", action: #selector(restartServer), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    // MARK: - Python Server

    func startServer() {
        // Kill any existing process on the port
        let killTask = Process()
        killTask.executableURL = URL(fileURLWithPath: "/bin/sh")
        killTask.arguments = ["-c", "lsof -ti:\(port) | xargs kill -9 2>/dev/null || true"]
        try? killTask.run()
        killTask.waitUntilExit()

        // Find python3
        let pythonPath = findPython()

        guard FileManager.default.fileExists(atPath: pythonScript) else {
            DispatchQueue.main.async {
                let alert = NSAlert()
                alert.messageText = "Dashboard Not Found"
                alert.informativeText = "Could not find claude-sessions-dashboard.py at:\n\(self.pythonScript)\n\nPlease ensure the file exists."
                alert.alertStyle = .critical
                alert.runModal()
            }
            return
        }

        serverProcess = Process()
        serverProcess?.executableURL = URL(fileURLWithPath: pythonPath)
        serverProcess?.arguments = [pythonScript]
        serverProcess?.standardOutput = FileHandle.nullDevice
        serverProcess?.standardError = FileHandle.nullDevice

        do {
            try serverProcess?.run()
        } catch {
            print("Failed to start server: \(error)")
        }
    }

    func stopServer() {
        serverProcess?.terminate()
        serverProcess = nil

        // Also kill by port in case of orphans
        let killTask = Process()
        killTask.executableURL = URL(fileURLWithPath: "/bin/sh")
        killTask.arguments = ["-c", "lsof -ti:\(port) | xargs kill -9 2>/dev/null || true"]
        try? killTask.run()
        killTask.waitUntilExit()
    }

    func findPython() -> String {
        let candidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ]
        for path in candidates {
            if FileManager.default.fileExists(atPath: path) {
                return path
            }
        }
        return "/usr/bin/python3"
    }

    func waitForServerAndOpenWindow() {
        DispatchQueue.global().async { [weak self] in
            guard let self = self else { return }
            let url = URL(string: "http://127.0.0.1:\(self.port)/")!

            // Poll until server responds (max 10 seconds)
            for _ in 0..<40 {
                usleep(250_000)  // 250ms
                var request = URLRequest(url: url)
                request.timeoutInterval = 1
                let semaphore = DispatchSemaphore(value: 0)
                var success = false

                let task = URLSession.shared.dataTask(with: request) { _, response, _ in
                    if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                        success = true
                    }
                    semaphore.signal()
                }
                task.resume()
                semaphore.wait()

                if success {
                    DispatchQueue.main.async {
                        self.createWindow()
                    }
                    return
                }
            }

            DispatchQueue.main.async {
                let alert = NSAlert()
                alert.messageText = "Server Failed"
                alert.informativeText = "Could not connect to the dashboard server on port \(self.port) after 10 seconds."
                alert.alertStyle = .critical
                alert.runModal()
            }
        }
    }

    // MARK: - Window & WebView

    func createWindow() {
        // Get screen size for a good default
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1400, height: 900)
        let windowWidth = min(screenRect.width * 0.85, 1600)
        let windowHeight = min(screenRect.height * 0.85, 1000)
        let windowX = screenRect.origin.x + (screenRect.width - windowWidth) / 2
        let windowY = screenRect.origin.y + (screenRect.height - windowHeight) / 2

        let windowRect = NSRect(x: windowX, y: windowY, width: windowWidth, height: windowHeight)

        window = NSWindow(
            contentRect: windowRect,
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Claude Sessions Dashboard"
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(red: 0.051, green: 0.067, blue: 0.09, alpha: 1.0)  // #0d1117
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 800, height: 500)

        // Configure WebView
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")  // Transparent background to match window

        let url = URL(string: "http://127.0.0.1:\(port)/")!
        webView.load(URLRequest(url: url))

        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: - Menu Actions

    @objc func openDashboard() {
        if window == nil {
            createWindow()
        } else {
            window.makeKeyAndOrderFront(nil)
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func refreshDashboard() {
        webView?.reload()
    }

    @objc func restartServer() {
        stopServer()
        startServer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
            self?.webView?.reload()
        }
    }

    @objc func quitApp() {
        stopServer()
        NSApp.terminate(nil)
    }
}

// MARK: - Main Entry Point

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
