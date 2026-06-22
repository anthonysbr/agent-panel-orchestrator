class AgentPanelOrchestrator < Formula
  include Language::Python::Virtualenv

  desc "Run independent agent panels through Codex, Claude Code, Cursor, and Gemini CLIs"
  homepage "https://github.com/anthonysbr/agent-panel-orchestrator"
  url "https://github.com/anthonysbr/agent-panel-orchestrator/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "bd6ed0505f790c71e0818877d79706843fe95d68e4834f012a52393c00279105"
  license "MIT"
  head "https://github.com/anthonysbr/agent-panel-orchestrator.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_create(libexec, Formula["python@3.12"].opt_bin/"python3")
    system libexec/"bin/pip", "install", *std_pip_args(build_isolation: true), "."
  end

  test do
    assert_match "design", shell_output("#{bin}/panel skills list")
  end
end
