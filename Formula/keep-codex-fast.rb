class KeepCodexFast < Formula
  desc "Codex desktop maintenance skill, automation, and CLI"
  homepage "https://github.com/k0nkupa/keep-codex-fast"
  url "https://github.com/k0nkupa/keep-codex-fast/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"
  head "https://github.com/k0nkupa/keep-codex-fast.git", branch: "main"

  depends_on "node"
  depends_on "python@3.13"

  def install
    libexec.install Dir["*"]
    bin.write_exec_script libexec/"bin/keep-codex-fast.js"
  end

  test do
    system bin/"keep-codex-fast", "--version"
  end
end
