class MoonshineFlow < Formula
  desc "Push-to-talk transcription daemon for macOS using Moonshine"
  homepage "https://github.com/MadHatterNakashima/moonshine-flow"
  # stable-release: updated by GitHub Actions on release publish.
  # stable-release-start
  url "https://github.com/NAKAK10/moonshine-flow/archive/refs/tags/v0.0.1-beta.4.tar.gz"
  sha256 "1789b5e8086cb92b6ae47c581ad64e054747e190703843745f8d7747f45e78af"
  version "0.0.1-beta.4"
  # stable-release-end
  head "https://github.com/MadHatterNakashima/moonshine-flow.git", branch: "main"
  preserve_rpath

  depends_on "portaudio"
  depends_on "python@3.11"
  depends_on "uv"

  def install
    libexec.install buildpath.children

    python = Formula["python@3.11"].opt_bin/"python3.11"
    ENV["UV_PYTHON"] = python
    ENV["UV_PYTHON_DOWNLOADS"] = "never"
    system "uv", "sync", "--project", libexec, "--frozen"

    (bin/"moonshine-flow").write_env_script libexec/".venv/bin/moonshine-flow", {
      "UV_PROJECT" => libexec.to_s,
      "UV_PYTHON" => python.to_s,
      "UV_PYTHON_DOWNLOADS" => "never",
    }
  end

  test do
    assert_match "moonshine-flow", shell_output("#{bin}/moonshine-flow --help")
  end
end
