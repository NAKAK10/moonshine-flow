class MoonshineFlow < Formula
  desc "Push-to-talk transcription daemon for macOS using Moonshine"
  homepage "https://github.com/MadHatterNakashima/moonshine-flow"
  # stable-release: updated by GitHub Actions on release publish.
  # stable-release-start
  # stable-release-end
  head "https://github.com/MadHatterNakashima/moonshine-flow.git", branch: "main"

  depends_on "portaudio"
  depends_on "uv"

  def install
    libexec.install buildpath.children

    system "uv", "sync", "--project", libexec, "--frozen"

    (bin/"moonshine-flow").write_env_script libexec/".venv/bin/moonshine-flow", {
      "UV_PROJECT" => libexec.to_s,
    }
  end

  test do
    assert_match "moonshine-flow", shell_output("#{bin}/moonshine-flow --help")
  end
end
