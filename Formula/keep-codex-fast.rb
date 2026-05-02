class KeepCodexFast < Formula
  desc "Codex desktop maintenance skill, automation, and CLI"
  homepage "https://github.com/k0nkupa/keep-codex-fast"
  url "https://github.com/k0nkupa/keep-codex-fast/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "e22fabeed382392e52d785495dbd670740c2c3161a7e6315cc7d385772e262a1"
  license "MIT"
  head "https://github.com/k0nkupa/keep-codex-fast.git", branch: "main"

  depends_on "node"
  depends_on "python@3.13"

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"bin/keep-codex-fast.js" => "keep-codex-fast"
  end

  test do
    system bin/"keep-codex-fast", "--version"
  end
end
