class ClaudeSessionsDashboard < Formula
  desc "Local web dashboard to view and manage Claude Code sessions"
  homepage "https://github.com/Yashokeerti/claude-sessions-dashboard"
  url "https://github.com/Yashokeerti/claude-sessions-dashboard/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "b58f511b43780efd277526f578d3c2fd31c0772555b426d62c9e19447f0ad64f"
  license "MIT"

  depends_on "python@3"

  def install
    # Install Python package
    libexec.install Dir["src/*"]
    libexec.install "pyproject.toml"

    # Create wrapper script
    (bin/"claude-sessions").write <<~EOS
      #!/bin/bash
      exec "#{Formula["python@3"].opt_bin}/python3" -c "
      import sys
      sys.path.insert(0, '#{libexec}/claude_sessions_dashboard')
      from dashboard import main
      main()
      " "$@"
    EOS
  end

  def caveats
    <<~EOS
      To start the dashboard:
        claude-sessions

      To use a custom port:
        claude-sessions --port 9090

      Then open http://localhost:8050 in your browser.

      Optional: Add a local domain for easy access:
        sudo sh -c 'echo "127.0.0.1 claude-sessions.mac" >> /etc/hosts'
        Then visit http://claude-sessions.mac:8050
    EOS
  end

  service do
    run [opt_bin/"claude-sessions"]
    keep_alive true
    log_path var/"log/claude-sessions-dashboard.log"
    error_log_path var/"log/claude-sessions-dashboard.log"
  end

  test do
    # Verify the script can be imported
    system Formula["python@3"].opt_bin/"python3", "-c",
           "import sys; sys.path.insert(0, '#{libexec}/claude_sessions_dashboard'); import dashboard"
  end
end
