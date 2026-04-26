#!/bin/bash
set -e

APP_NAME="Claude Sessions"
BUNDLE_NAME="Claude Sessions.app"
BUILD_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$BUILD_DIR/.." && pwd)"
APP_DIR="$BUILD_DIR/$BUNDLE_NAME"

echo "Building $APP_NAME..."

# Clean previous build
rm -rf "$APP_DIR"

# Create .app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Copy Info.plist
cp "$BUILD_DIR/Info.plist" "$APP_DIR/Contents/"

# Copy the Python dashboard script into Resources
cp "$REPO_DIR/src/claude_sessions_dashboard/dashboard.py" "$APP_DIR/Contents/Resources/claude-sessions-dashboard.py"

# Copy icons
cp "$BUILD_DIR/AppIcon.icns" "$APP_DIR/Contents/Resources/"
if [ -f "$BUILD_DIR/icon.png" ]; then
    cp "$BUILD_DIR/icon.png" "$APP_DIR/Contents/Resources/"
fi

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    TARGET="arm64-apple-macos13"
else
    TARGET="x86_64-apple-macos13"
fi

# Compile Swift
echo "Compiling Swift for $ARCH..."
swiftc \
    -o "$APP_DIR/Contents/MacOS/ClaudeSessions" \
    -framework Cocoa \
    -framework WebKit \
    -target "$TARGET" \
    "$BUILD_DIR/ClaudeSessions.swift"

echo "Build complete: $APP_DIR"
echo ""

# Install to ~/Applications
echo "Installing to ~/Applications..."
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/$BUNDLE_NAME"
cp -R "$APP_DIR" "$HOME/Applications/"
echo "Installed to ~/Applications/$BUNDLE_NAME"
echo ""
echo "You can now:"
echo "  1. Open from Finder: ~/Applications/$BUNDLE_NAME"
echo "  2. Open from terminal: open ~/Applications/Claude\ Sessions.app"
echo "  3. Add to Dock: drag from ~/Applications"
echo "  4. Search in Spotlight: 'Claude Sessions'"
